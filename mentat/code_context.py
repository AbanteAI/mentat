import asyncio
import os
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Optional

import attr

from .code_file import CodeFile, CodeMessageLevel
from .code_map import check_ctags_disabled
from .config_manager import ConfigManager
from .diff_context import DiffContext, get_diff_context
from .errors import MentatError, UserError
from .git_handler import get_non_gitignored_files, get_paths_with_git_diffs
from .include_files import (
    build_path_tree,
    get_include_files,
    is_file_text_encoded,
    print_path_tree,
)
from .llm_api import count_tokens
from .session_stream import SESSION_STREAM
from .utils import sha256

if TYPE_CHECKING:
    # These normally will cause a circular import
    from mentat.code_file_manager import CodeFileManager
    from mentat.parsers.parser import Parser


def _longer_feature_already_included(
    feature: CodeFile, features: list[CodeFile]
) -> bool:
    for f in features:
        if f.path != feature.path:
            continue
        elif f.diff and not feature.diff:
            return True
        elif f.level.rank < feature.level.rank:
            return True
    return False


def _shorter_features_already_included(
    feature: CodeFile, features: list[CodeFile]
) -> list[CodeFile]:
    to_replace = list[CodeFile]()
    for f in features:
        if f.path != feature.path:
            continue
        elif feature.diff and not f.diff:
            to_replace.append(f)
        elif f.level.rank > feature.level.rank:
            to_replace.append(f)
    return to_replace


@attr.define
class CodeContextSettings:
    paths: list[Path] = []
    exclude_paths: list[Path] = []
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False
    auto_tokens: Optional[int] = None

    def asdict(self):
        return attr.asdict(self)


class CodeContext:
    config: ConfigManager
    settings: CodeContextSettings
    include_files: dict[Path, CodeFile]
    diff_context: DiffContext
    code_map: bool = True
    features: list[CodeFile] = []

    def __init__(self, config: ConfigManager, settings: CodeContextSettings):
        self.config = config
        self.settings = settings

    @classmethod
    async def create(
        cls,
        config: ConfigManager,
        paths: list[Path],
        exclude_paths: list[Path],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        no_code_map: bool = False,
        auto_tokens: Optional[int] = None,
    ):
        settings = CodeContextSettings(
            paths=paths,
            exclude_paths=exclude_paths,
            diff=diff,
            pr_diff=pr_diff,
            no_code_map=no_code_map,
            auto_tokens=auto_tokens,
        )
        self = cls(config, settings)

        await self._set_diff_context(replace_paths=True)
        self._set_include_files()
        await self._set_code_map()

        return self

    async def _set_diff_context(self, replace_paths: bool = False):
        stream = SESSION_STREAM.get()
        try:
            self.diff_context = get_diff_context(
                self.config, self.settings.diff, self.settings.pr_diff
            )
            if replace_paths and not self.settings.paths:
                self.settings.paths = self.diff_context.files
        except UserError as e:
            await stream.send(str(e), color="light_yellow")
            exit()

    def _set_include_files(self):
        self.include_files = get_include_files(
            self.config, self.settings.paths, self.settings.exclude_paths
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

        await stream.send("\nCode Context:", color="blue")
        prefix = "  "
        await stream.send(f"{prefix}Directory: {self.config.git_root}")
        if self.diff_context.name:
            await stream.send(f"{prefix}Diff:", end=" ")
            await stream.send(self.diff_context.get_display_context(), color="green")
        if self.include_files:
            await stream.send(f"{prefix}Included files:")
            await stream.send(f"{prefix + prefix}{self.config.git_root.name}")
            await print_path_tree(
                build_path_tree(
                    list(self.include_files.values()), self.config.git_root
                ),
                get_paths_with_git_diffs(self.config.git_root),
                self.config.git_root,
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
            await SESSION_STREAM.get().send("Auto-Selected Features:", color="blue")
            for level, count in auto_features.items():
                if count:
                    print(f"  {count} {level.description}")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    async def _get_code_message_checksum(
        self, code_file_manager: "CodeFileManager", max_tokens: Optional[int] = None
    ) -> str:
        if not self.features:
            features_checksum = ""
        else:
            feature_files = {Path(self.config.git_root / f.path) for f in self.features}
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
        code_file_manager: "CodeFileManager",
        parser: "Parser",
        max_tokens: int,
    ) -> str:
        code_message_checksum = await self._get_code_message_checksum(
            code_file_manager, max_tokens
        )
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = await self._get_code_message(
                model, code_file_manager, parser, max_tokens
            )
            self._code_message_checksum = await self._get_code_message_checksum(
                code_file_manager, max_tokens
            )
        return self._code_message

    async def _get_code_message(
        self,
        model: str,
        code_file_manager: "CodeFileManager",
        parser: "Parser",
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
        include_feature_tokens_task = [
            f.count_tokens(self.config, code_file_manager, parser, model)
            for f in features
        ]
        results = await asyncio.gather(*include_feature_tokens_task)
        include_feature_tokens = sum(results) + count_tokens(
            "\n".join(code_message), model
        )
        _max_auto = max(0, max_tokens - include_feature_tokens)
        _max_user = self.settings.auto_tokens
        if _max_auto == 0 or _max_user == 0:
            self.features = features
        else:
            auto_tokens = _max_auto if _max_user is None else min(_max_auto, _max_user)
            self.features = await self._get_auto_features(
                code_file_manager, parser, model, features, auto_tokens
            )

        for f in self.features:
            code_message += await f.get_code_message(
                self.config, code_file_manager, parser
            )
        return "\n".join(code_message)

    def _get_include_features(self) -> list[CodeFile]:
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
            return os.path.relpath(f.path, self.config.git_root)

        return sorted(include_features, key=_feature_relative_path)

    async def _get_auto_features(
        self,
        code_file_manager: "CodeFileManager",
        parser: "Parser",
        model: str,
        include_features: list[CodeFile],
        max_tokens: int,
    ) -> list[CodeFile]:
        # Generate all possible permutations for all files in the project.
        candidate_features = list[CodeFile]()
        for path in get_non_gitignored_files(self.config.git_root):
            if not path.is_dir() and not is_file_text_encoded(path):
                continue
            permutations: list[tuple[CodeMessageLevel, str | None]] = [
                (CodeMessageLevel.CODE, None),
                (CodeMessageLevel.FILE_NAME, None),
            ]
            if not self.settings.no_code_map:
                permutations += [
                    (CodeMessageLevel.CMAP_FULL, None),
                    (CodeMessageLevel.CMAP, None),
                ]
            if self.diff_context.target and path in self.diff_context.files:
                permutations += [
                    (level, self.diff_context.target) for level, _ in permutations
                ]
            for level, diff in permutations:
                feature = CodeFile(path, level=level, diff=diff)
                candidate_features.append(feature)

        # Sort candidates by relevance/density.
        tokens_remaining = max_tokens
        sem = asyncio.Semaphore(10)

        async def _calculate_feature_score(feature: CodeFile) -> float:
            score = 0.0
            async with sem:
                tokens = await feature.count_tokens(
                    self.config, code_file_manager, parser, model
                )
            if tokens == 0:
                raise MentatError(f"Feature {feature} has 0 tokens.")
            if feature.diff is not None:
                score += 1
            if feature.level == CodeMessageLevel.FILE_NAME:
                score += 0.1
            if feature.level == CodeMessageLevel.CMAP:
                score += 0.25
            elif feature.level == CodeMessageLevel.CMAP_FULL:
                score += 0.5
            elif feature.level == CodeMessageLevel.CODE:
                score += 0.75
            score /= tokens
            return score

        all_features = include_features.copy()
        candidate_scores_task = [
            _calculate_feature_score(f) for f in candidate_features
        ]
        candidate_scores = await asyncio.gather(
            *candidate_scores_task, return_exceptions=True
        )
        candidates_scored = list(zip(candidate_features, candidate_scores))
        candidates_sorted = sorted(candidates_scored, key=lambda x: x[1], reverse=True)
        for feature, _ in candidates_sorted:
            feature_tokens = await feature.count_tokens(
                self.config, code_file_manager, parser, model
            )
            if tokens_remaining - feature_tokens <= 0:
                continue
            if _longer_feature_already_included(feature, all_features):
                continue
            to_replace = _shorter_features_already_included(feature, all_features)
            if to_replace:
                for f in to_replace:
                    f_index = all_features.index(f)
                    reclaimed_tokens = await all_features[f_index].count_tokens(
                        self.config, code_file_manager, parser, model
                    )
                    tokens_remaining += reclaimed_tokens
                    all_features = all_features[:f_index] + all_features[f_index + 1 :]
            all_features.append(feature)
            new_tokens = await feature.count_tokens(
                self.config, code_file_manager, parser, model
            )
            tokens_remaining -= new_tokens

        def _feature_relative_path(f: CodeFile) -> str:
            return os.path.relpath(f.path, self.config.git_root)

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
