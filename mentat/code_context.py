from __future__ import annotations

import asyncio
import os
from contextvars import ContextVar
from pathlib import Path
from textwrap import dedent
from typing import Optional

import attr

from .code_file import CodeFile, CodeMessageLevel
from .code_file_manager import CODE_FILE_MANAGER
from .code_map import check_ctags_disabled
from .diff_context import DiffContext
from .errors import UserError
from .git_handler import GIT_ROOT, get_non_gitignored_files, get_paths_with_git_diffs
from .include_files import (
    build_path_tree,
    get_include_files,
    is_file_text_encoded,
    print_path_tree,
)
from .llm_api import count_tokens
from .session_stream import SESSION_STREAM
from .utils import sha256


async def _count_tokens_in_features(features: list[CodeFile], model: str) -> int:
    sem = asyncio.Semaphore(10)

    async def _count_tokens(feature: CodeFile) -> int:
        async with sem:
            return await feature.count_tokens(model)

    tasks = [_count_tokens(f) for f in features]
    results = await asyncio.gather(*tasks)
    return sum(results)


@attr.define
class CodeContextSettings:
    paths: list[Path] = []
    exclude_paths: list[Path] = []
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False
    auto_tokens: Optional[int] = None


CODE_CONTEXT: ContextVar[CodeContext] = ContextVar("mentat:code_context")


class CodeContext:
    settings: CodeContextSettings
    include_files: dict[Path, CodeFile]
    diff_context: DiffContext
    code_map: bool = True
    features: list[CodeFile] = []

    def __init__(self, settings: CodeContextSettings):
        self.settings = settings

    @classmethod
    async def create(cls, settings: CodeContextSettings):
        self = cls(settings)

        await self._set_diff_context(replace_paths=True)
        self._set_include_files()
        await self._set_code_map()

        return self

    async def _set_diff_context(self, replace_paths: bool = False):
        try:
            self.diff_context = DiffContext.create(
                self.settings.diff, self.settings.pr_diff
            )
            if replace_paths and not self.settings.paths:
                self.settings.paths = self.diff_context.files
        except UserError as e:
            await SESSION_STREAM.get().send(str(e), color="light_yellow")
            exit()

    def _set_include_files(self):
        self.include_files = get_include_files(
            self.settings.paths, self.settings.exclude_paths
        )

    async def _set_code_map(self):
        if self.settings.no_code_map:
            self.code_map = False
        else:
            disabled_reason = await check_ctags_disabled()
            if disabled_reason:
                ctags_disabled_message = f"""
                    There was an error with your universal ctags installation, disabling CodeMap.
                    Reason: {disabled_reason}
                """
                ctags_disabled_message = dedent(ctags_disabled_message)
                await SESSION_STREAM.get().send(ctags_disabled_message, color="yellow")
                self.settings.no_code_map = True
                self.code_map = False
            else:
                self.code_map = True

    async def display_context(self):
        """Display the baseline context: included files and auto-context settings"""
        stream = SESSION_STREAM.get()
        git_root = GIT_ROOT.get()

        await stream.send("\nCode Context:", color="blue")
        prefix = "  "
        await stream.send(f"{prefix}Directory: {git_root}")
        if self.diff_context.name:
            await stream.send(f"{prefix}Diff:", end=" ")
            await stream.send(self.diff_context.get_display_context(), color="green")
        if self.include_files:
            await stream.send(f"{prefix}Included files:")
            await stream.send(f"{prefix + prefix}{git_root.name}")
            await print_path_tree(
                build_path_tree(list(self.include_files.values()), git_root),
                get_paths_with_git_diffs(),
                git_root,
                prefix + prefix,
            )
        else:
            await stream.send(f"{prefix}Included files: None", color="yellow")
        await stream.send(
            f"{prefix}CodeMaps: {'Enabled' if self.code_map else 'Disabled'}"
        )
        auto = self.settings.auto_tokens
        await stream.send(
            f"{prefix}Auto-tokens: {'Model max (default)' if auto is None else auto}"
        )

    async def display_features(self):
        """Display a summary of all active features"""
        auto_features = {level: 0 for level in CodeMessageLevel}
        for f in self.features:
            if f.path not in self.include_files:
                auto_features[f.level] += 1
        if any(auto_features.values()):
            stream = SESSION_STREAM.get()
            await stream.send("Auto-Selected Features:", color="blue")
            for level, count in auto_features.items():
                if count:
                    await stream.send(f"  {count} {level.description}")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    def _get_code_message_checksum(self, max_tokens: Optional[int] = None) -> str:
        if not self.features:
            features_checksum = ""
        else:
            git_root = GIT_ROOT.get()
            code_file_manager = CODE_FILE_MANAGER.get()
            feature_files = {Path(git_root / f.path) for f in self.features}
            feature_file_checksums = [
                code_file_manager.get_file_checksum(f) for f in feature_files
            ]
            features_checksum = sha256("".join(feature_file_checksums))
        settings = attr.asdict(self.settings)
        settings["max_tokens"] = max_tokens
        settings_checksum = sha256(str(settings))
        return features_checksum + settings_checksum

    async def get_code_message(
        self,
        model: str,
        max_tokens: int,
    ) -> str:
        code_message_checksum = self._get_code_message_checksum(max_tokens)
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = await self._get_code_message(model, max_tokens)
            self._code_message_checksum = self._get_code_message_checksum(max_tokens)
        return self._code_message

    async def _get_code_message(
        self,
        model: str,
        max_tokens: int,
    ) -> str:
        code_message = list[str]()

        await self._set_diff_context()
        self._set_include_files()
        await self._set_code_map()
        if self.diff_context.files:
            code_message += [
                "Diff References:",
                f' "-" = {self.diff_context.name}',
                ' "+" = Active Changes',
                "",
            ]
        code_message += ["Code Files:\n"]

        features = self._get_include_features()
        include_feature_tokens = await _count_tokens_in_features(
            features, model
        ) - count_tokens("\n".join(code_message), model)
        _max_auto = max(0, max_tokens - include_feature_tokens)
        _max_user = self.settings.auto_tokens
        if _max_auto == 0 or _max_user == 0:
            self.features = features
        else:
            auto_tokens = _max_auto if _max_user is None else min(_max_auto, _max_user)
            self.features = await self._get_auto_features(model, features, auto_tokens)

        for f in self.features:
            code_message += await f.get_code_message()
        return "\n".join(code_message)

    def _get_include_features(self) -> list[CodeFile]:
        git_root = GIT_ROOT.get()
        include_features = list[CodeFile]()
        for path, feature in self.include_files.items():
            if feature.level == CodeMessageLevel.INTERVAL:
                interval_str = ",".join(f"{i.start}-{i.end}" for i in feature.intervals)
                path = f"{path}:{interval_str}"
            diff_target = (
                self.diff_context.target if path in self.diff_context.files else None
            )
            feature = CodeFile(path, feature.level, diff=diff_target)
            include_features.append(feature)

        def _feature_relative_path(f: CodeFile) -> str:
            return os.path.relpath(f.path, git_root)

        return sorted(include_features, key=_feature_relative_path)

    async def _get_auto_features(
        self,
        model: str,
        include_features: list[CodeFile],
        max_tokens: int,
    ) -> list[CodeFile]:
        git_root = GIT_ROOT.get()

        # Find the first (longest) level that fits
        include_features_tokens = await _count_tokens_in_features(
            include_features, model
        )
        max_auto_tokens = max_tokens - include_features_tokens
        all_features = include_features.copy()
        levels = [CodeMessageLevel.FILE_NAME]
        if not self.settings.no_code_map:
            levels = [CodeMessageLevel.CMAP_FULL, CodeMessageLevel.CMAP] + levels
        for level in levels:
            _features = list[CodeFile]()
            for path in get_non_gitignored_files(git_root):
                if (
                    path in self.include_files
                    or path.is_dir()
                    or not is_file_text_encoded(path)
                ):
                    continue
                diff_target = (
                    self.diff_context.target
                    if path in self.diff_context.files
                    else None
                )
                feature = CodeFile(path, level=level, diff=diff_target)
                _features.append(feature)
            level_length = await _count_tokens_in_features(_features, model)
            if level_length < max_auto_tokens:
                all_features += _features
                break

        def _feature_relative_path(f: CodeFile) -> str:
            return os.path.relpath(f.path, git_root)

        return sorted(all_features, key=_feature_relative_path)

    async def include_file(self, code_file: CodeFile):
        stream = SESSION_STREAM.get()
        if not os.path.exists(code_file.path):
            await stream.send(f"File does not exist: {code_file.path}\n", color="red")
            return
        if code_file.path in self.settings.paths:
            await stream.send(
                f"File already in context: {code_file.path}\n", color="yellow"
            )
            return
        if code_file.path in self.settings.exclude_paths:
            self.settings.exclude_paths.remove(code_file.path)
        self.settings.paths.append(code_file.path)
        self._set_include_files()
        await stream.send(
            f"File included in context: {code_file.path}\n", color="green"
        )

    async def exclude_file(self, code_file: CodeFile):
        stream = SESSION_STREAM.get()
        if not os.path.exists(code_file.path):
            await stream.send(f"File does not exist: {code_file.path}\n", color="red")
            return
        if code_file.path not in self.settings.paths:
            await stream.send(
                f"File not in context: {code_file.path}\n", color="yellow"
            )
            return
        if code_file.path in self.settings.exclude_paths:
            self.settings.paths.remove(code_file.path)
        self.settings.exclude_paths.append(code_file.path)
        self._set_include_files()
        await stream.send(
            f"File removed from context: {code_file.path}\n", color="green"
        )
