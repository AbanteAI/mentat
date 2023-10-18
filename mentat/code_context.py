from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path
from textwrap import dedent
from typing import Optional

import attr

from .code_file import CodeFile, CodeMessageLevel, count_feature_tokens
from .code_file_manager import CODE_FILE_MANAGER
from .code_map import check_ctags_disabled
from .diff_context import DiffContext
from .embeddings import get_feature_similarity_scores
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


@attr.define
class CodeContextSettings:
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False
    use_embedding: bool = False
    auto_tokens: Optional[int] = None


CODE_CONTEXT: ContextVar[CodeContext] = ContextVar("mentat:code_context")


class CodeContext:
    settings: CodeContextSettings
    include_files: dict[Path, CodeFile]
    diff_context: DiffContext
    code_map: bool = True
    features: list[CodeFile] = []

    def __init__(
        self,
        settings: CodeContextSettings,
    ):
        self.settings = settings

    @classmethod
    async def create(
        cls, paths: list[Path], exclude_paths: list[Path], settings: CodeContextSettings
    ):
        stream = SESSION_STREAM.get()

        self = cls(settings)

        self.diff_context = await DiffContext.create(
            self.settings.diff, self.settings.pr_diff
        )
        self.include_files, invalid_paths = get_include_files(paths, exclude_paths)
        for invalid_path in invalid_paths:
            await stream.send(
                f"File path {invalid_path} is not text encoded, and was skipped.",
                color="light_yellow",
            )
        await self._set_code_map()

        return self

    async def _set_code_map(self):
        stream = SESSION_STREAM.get()

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
                await stream.send(ctags_disabled_message, color="yellow")
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
        settings["include_files"] = self.include_files
        settings_checksum = sha256(str(settings))
        return features_checksum + settings_checksum

    async def get_code_message(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str:
        code_message_checksum = self._get_code_message_checksum(max_tokens)
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = await self._get_code_message(prompt, model, max_tokens)
            self._code_message_checksum = self._get_code_message_checksum(max_tokens)
        return self._code_message

    async def _get_code_message(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str:
        code_message = list[str]()

        self.diff_context.clear_cache
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
        include_feature_tokens = sum(await count_feature_tokens(features, model))
        include_feature_tokens -= count_tokens("\n".join(code_message), model)
        _max_auto = max(0, max_tokens - include_feature_tokens)
        _max_user = self.settings.auto_tokens
        if _max_auto == 0 or _max_user == 0:
            self.features = features
        else:
            auto_tokens = _max_auto if _max_user is None else min(_max_auto, _max_user)
            self.features = await self._get_auto_features(
                prompt, model, features, auto_tokens
            )

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
        prompt: str,
        model: str,
        include_features: list[CodeFile],
        max_tokens: int,
    ) -> list[CodeFile]:
        git_root = GIT_ROOT.get()

        # Find the first (longest) level that fits
        include_features_tokens = sum(
            await count_feature_tokens(include_features, model)
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
            level_length = sum(await count_feature_tokens(_features, model))
            if level_length < max_auto_tokens:
                all_features += _features
                break

        # Sort by relative path
        def _feature_relative_path(f: CodeFile) -> str:
            return os.path.relpath(f.path, git_root)

        all_features = sorted(all_features, key=_feature_relative_path)

        # If there's room, convert cmap features to code features (full text)
        # starting with the highest-scoring.
        cmap_features_tokens = sum(await count_feature_tokens(all_features, model))
        max_sim_tokens = max_tokens - cmap_features_tokens
        if self.settings.auto_tokens is not None:
            max_sim_tokens = min(max_sim_tokens, self.settings.auto_tokens)

        if self.settings.use_embedding and max_sim_tokens > 0 and prompt != "":
            sim_tokens = 0

            # Get embedding-similarity scores for all files
            all_code_features = [
                CodeFile(f.path, CodeMessageLevel.CODE, f.diff)
                for f in all_features
                if f.path not in self.include_files
            ]
            sim_scores = await get_feature_similarity_scores(prompt, all_code_features)
            all_code_features_scored = zip(all_code_features, sim_scores)
            all_code_features_sorted = sorted(
                all_code_features_scored, key=lambda x: x[1], reverse=True
            )
            for code_feature, _ in all_code_features_sorted:
                # Calculate the total change in length
                i_cmap, cmap_feature = next(
                    (i, f)
                    for i, f in enumerate(all_features)
                    if f.path == code_feature.path
                )
                recovered_tokens = await cmap_feature.count_tokens(model)
                new_tokens = await code_feature.count_tokens(model)
                forecast = max_sim_tokens - sim_tokens + recovered_tokens - new_tokens
                if forecast > 0:
                    sim_tokens = sim_tokens + new_tokens - recovered_tokens
                    all_features[i_cmap] = code_feature

        return sorted(all_features, key=_feature_relative_path)

    def include_file(self, path: Path):
        paths, invalid_paths = get_include_files([path], [])
        for new_path, new_file in paths.items():
            if new_path not in self.include_files:
                self.include_files[new_path] = new_file
        return invalid_paths

    def exclude_file(self, path: Path):
        paths, _ = get_include_files([path], [])
        for new_path in paths.keys():
            if new_path in self.include_files:
                del self.include_files[new_path]
