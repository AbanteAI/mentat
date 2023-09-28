import os
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Optional

import attr
from termcolor import cprint

from .code_file import CodeFile, CodeMessageLevel
from .code_map import check_ctags_disabled
from .config_manager import ConfigManager
from .diff_context import DiffContext, get_diff_context
from .errors import UserError
from .git_handler import get_non_gitignored_files, get_paths_with_git_diffs
from .include_files import build_path_tree, get_include_files, print_path_tree
from .utils import sha256

if TYPE_CHECKING:
    # This normally will cause a circular import
    from mentat.code_file_manager import CodeFileManager


_feature_order = [
    CodeMessageLevel.CODE,
    CodeMessageLevel.INTERVAL,
    CodeMessageLevel.CMAP_FULL,
    CodeMessageLevel.CMAP,
    CodeMessageLevel.FILE_NAME,
]


def _longer_feature_already_included(
    feature: CodeFile, features: list[CodeFile]
) -> bool:
    for f in features:
        if f.path != feature.path:
            continue
        elif f.diff and not feature.diff:
            return True
        elif _feature_order.index(f.level) < _feature_order.index(feature.level):
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
        elif _feature_order.index(f.level) > _feature_order.index(feature.level):
            to_replace.append(f)
    return to_replace


@attr.define
class CodeContextSettings:
    paths: list[Path]
    exclude_paths: list[Path]
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False
    max_tokens: int = 8192


class CodeContext:
    config: ConfigManager
    settings: CodeContextSettings
    include_files: dict[Path, CodeFile]
    diff_context: DiffContext
    code_map: bool = True
    features: list[CodeFile] = []

    def __init__(
        self,
        config: ConfigManager,
        paths: list[Path],
        exclude_paths: list[Path],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        no_code_map: bool = False,
        max_tokens: int = 8192,
    ):
        self.config = config
        self.settings = CodeContextSettings(
            paths=paths,
            exclude_paths=exclude_paths,
            diff=diff,
            pr_diff=pr_diff,
            no_code_map=no_code_map,
            max_tokens=max_tokens,
        )

        self._set_diff_context(replace_paths=True)
        self._set_include_files()
        self._set_code_map()

    def _set_diff_context(self, replace_paths: bool = False):
        try:
            self.diff_context = get_diff_context(
                self.config, self.settings.diff, self.settings.pr_diff
            )
            if replace_paths and not self.settings.paths:
                self.settings.paths = self.diff_context.files
        except UserError as e:
            cprint(str(e), "light_yellow")
            exit()

    def _set_include_files(self):
        self.include_files = get_include_files(
            self.config, self.settings.paths, self.settings.exclude_paths
        )

    def _set_code_map(self):
        if self.settings.no_code_map:
            self.code_map = False
        else:
            disabled_reason = check_ctags_disabled()
            if disabled_reason:
                ctags_disabled_message = f"""
                    There was an error with your universal ctags installation, disabling CodeMap.
                    Reason: {disabled_reason}
                """
                ctags_disabled_message = dedent(ctags_disabled_message)
                cprint(ctags_disabled_message, color="yellow")
                self.code_map = False
            else:
                self.code_map = True

    def display_context(self):
        if self.include_files:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(self.config.git_root.name, "blue")
        print_path_tree(
            build_path_tree(list(self.include_files.values()), self.config.git_root),
            get_paths_with_git_diffs(self.config.git_root),
            self.config.git_root,
        )
        print()
        self.diff_context.display_context()
        print()
        if self.code_map:
            cprint("Including CodeMaps", "green")
        else:
            cprint("Code Maps disabled", "yellow")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    def _get_code_message_checksum(self, code_file_manager: "CodeFileManager") -> str:
        if not self.features:
            features_checksum = ""
        else:
            feature_files = {Path(self.config.git_root / f.path) for f in self.features}
            feature_file_checksums = [
                code_file_manager.get_file_checksum(f) for f in feature_files
            ]
            features_checksum = sha256("".join(feature_file_checksums))
        settings_checksum = sha256(str(self.settings))
        return features_checksum + settings_checksum

    def get_code_message(self, model: str, code_file_manager: "CodeFileManager") -> str:
        code_message_checksum = self._get_code_message_checksum(code_file_manager)
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = self._get_code_message(model, code_file_manager)
            self._code_message_checksum = self._get_code_message_checksum(
                code_file_manager
            )
        return self._code_message

    def _get_code_message(
        self, model: str, code_file_manager: "CodeFileManager"
    ) -> str:
        code_message = list[str]()

        self._set_diff_context()
        self._set_include_files()
        self._set_code_map()
        if self.diff_context.files:
            code_message += [
                "Diff References:",
                f' "-" = {self.diff_context.name}',
                ' "+" = Active Changes',
                "",
            ]

        code_message += ["Code Files:\n"]

        # Initalize all features while splitting into include and candidate
        include_features = list[CodeFile]()
        candidate_features = list[CodeFile]()
        for path in get_non_gitignored_files(self.config.git_root):
            permutations: list[tuple[CodeMessageLevel, str | None]] = [
                (CodeMessageLevel.CODE, None),
                (CodeMessageLevel.CMAP_FULL, None),
                (CodeMessageLevel.CMAP, None),
                (CodeMessageLevel.FILE_NAME, None),
            ]
            for level, diff in permutations:
                feature = CodeFile(path, level=level, diff=diff)
                diff_target = (
                    self.diff_context.target
                    if path in self.diff_context.files
                    else None
                )
                if diff_target is not None:
                    candidate_features.append(feature)
                    feature = CodeFile(path, level=level, diff=diff_target)
                included_path = self.include_files.get(feature.path.absolute())
                if included_path and level == CodeMessageLevel.CODE:
                    if included_path.level == CodeMessageLevel.INTERVAL:
                        candidate_features.append(feature)
                        interval_str = ",".join(
                            f"{i.start}-{i.end}" for i in included_path.intervals
                        )
                        feature = CodeFile(
                            path=f"{feature.path}:{interval_str}",
                            level=CodeMessageLevel.INTERVAL,
                            diff=diff_target,
                        )
                    include_features.append(feature)
                else:
                    candidate_features.append(feature)
        include_feature_tokens = sum(
            f.count_tokens(self.config, code_file_manager, model)
            for f in include_features
        )
        tokens_remaining = self.settings.max_tokens - include_feature_tokens
        # If required features exceed settings.max_tokens, return them directly.
        if tokens_remaining <= 0:
            self.features = sorted(
                include_features,
                key=lambda x: os.path.relpath(x.path, self.config.git_root),
            )
            for f in self.features:
                code_message += f.get_code_message(self.config, code_file_manager)
            return "\n".join(code_message)

        # If extra space, sort candidates by relevance/density and fill-in features.
        def _calculate_feature_score(feature: CodeFile) -> float:
            score = 0.0
            tokens = feature.count_tokens(self.config, code_file_manager, model)
            if tokens < tokens_remaining:
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

        candidates_sorted = sorted(
            candidate_features, key=lambda x: _calculate_feature_score(x), reverse=True
        )
        all_features = include_features.copy()
        for feature in candidates_sorted:
            if (
                tokens_remaining
                - feature.count_tokens(self.config, code_file_manager, model)
                <= 0
            ):
                continue
            if _longer_feature_already_included(feature, all_features):
                continue
            to_replace = _shorter_features_already_included(feature, all_features)
            if to_replace:
                for f in to_replace:
                    f_index = all_features.index(f)
                    tokens_remaining += all_features[f_index].count_tokens(
                        self.config, code_file_manager, model
                    )
                    all_features = all_features[:f_index] + all_features[f_index + 1 :]
            all_features.append(feature)
            tokens_remaining -= feature.count_tokens(
                self.config, code_file_manager, model
            )
        self.features = sorted(
            all_features, key=lambda x: os.path.relpath(x.path, self.config.git_root)
        )
        for f in self.features:
            code_message += f.get_code_message(self.config, code_file_manager)
        return "\n".join(code_message)

    def include_file(self, code_file: CodeFile):
        if not os.path.exists(code_file.path):
            cprint(f"File does not exist: {code_file.path}\n", "red")
            return
        if code_file.path in self.include_files:
            cprint(f"File already in context: {code_file.path}\n", "yellow")
            return
        if code_file.path in self.settings.exclude_paths:
            self.settings.exclude_paths.remove(code_file.path)
        self.settings.paths.append(code_file.path)
        cprint(f"File included in context: {code_file.path}\n", "green")

    def exclude_file(self, code_file: CodeFile):
        if not os.path.exists(code_file.path):
            cprint(f"File does not exist: {code_file.path}\n", "red")
            return
        if code_file.path not in self.include_files:
            cprint(f"File not in context: {code_file.path}\n", "yellow")
            return
        del self.include_files[code_file.path]
        cprint(f"File removed from context: {code_file.path}\n", "green")
