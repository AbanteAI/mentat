import os
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Optional

import attr
from termcolor import cprint

from mentat.llm_api import count_tokens

from .code_file import CodeFile, CodeMessageLevel
from .code_map import check_ctags_disabled
from .config_manager import ConfigManager
from .diff_context import DiffContext, get_diff_context
from .errors import MentatError, UserError
from .git_handler import get_non_gitignored_files, get_paths_with_git_diffs
from .include_files import build_path_tree, get_include_files, print_path_tree
from .utils import sha256

if TYPE_CHECKING:
    # This normally will cause a circular import
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
    paths: list[Path]
    exclude_paths: list[Path]
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False
    auto_tokens: Optional[int] = None


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
        auto_tokens: Optional[int] = None,
    ):
        self.config = config
        self.settings = CodeContextSettings(
            paths=paths,
            exclude_paths=exclude_paths,
            diff=diff,
            pr_diff=pr_diff,
            no_code_map=no_code_map,
            auto_tokens=auto_tokens,
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
        """Display the baseline context: included files and auto-context settings"""
        cprint("\nCode Context:", "blue")
        prefix = "  "
        cprint(f"{prefix}Directory: {self.config.git_root}")
        if self.diff_context.name:
            cprint(f"{prefix}Diff:", end=" ")
            cprint(self.diff_context.get_display_context(), color="green")
        if self.include_files:
            cprint(f"{prefix}Included files:")
            cprint(f"{prefix + prefix}{self.config.git_root.name}")
            print_path_tree(
                build_path_tree(
                    list(self.include_files.values()), self.config.git_root
                ),
                get_paths_with_git_diffs(self.config.git_root),
                self.config.git_root,
                prefix + prefix,
            )
        else:
            cprint(f"{prefix}Included files: None", "yellow")
        cprint(f"{prefix}CodeMaps: {'Enabled' if self.code_map else 'Disabled'}")
        auto = self.settings.auto_tokens
        cprint(
            f"{prefix}Auto-tokens: {'Model max (default)' if auto is None else auto}"
        )

    def display_features(self):
        """Display a summary of all active features"""
        auto_features = {level: 0 for level in CodeMessageLevel}
        for f in self.features:
            if f.path not in self.include_files:
                auto_features[f.level] += 1
        if any(auto_features.values()):
            cprint("Auto-Selected Features:", "blue")
            for level, count in auto_features.items():
                if count:
                    print(f"  {count} {level.description}")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    def _get_code_message_checksum(
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

    def get_code_message(
        self,
        model: str,
        code_file_manager: "CodeFileManager",
        parser: "Parser",
        max_tokens: Optional[int] = None,
    ) -> str:
        code_message_checksum = self._get_code_message_checksum(
            code_file_manager, max_tokens
        )
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = self._get_code_message(
                model, code_file_manager, parser, max_tokens
            )
            self._code_message_checksum = self._get_code_message_checksum(
                code_file_manager, max_tokens
            )
        return self._code_message

    def _get_code_message(
        self,
        model: str,
        code_file_manager: "CodeFileManager",
        parser: "Parser",
        max_tokens: Optional[int] = None,
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

        features = self._get_include_features()
        include_feature_tokens = sum(
            f.count_tokens(self.config, code_file_manager, parser, model)
            for f in features
        ) + count_tokens("\n".join(code_message), model)
        _max_auto = (
            None if max_tokens is None else max(0, max_tokens - include_feature_tokens)
        )
        _max_user = self.settings.auto_tokens
        if _max_auto == 0 or _max_user == 0:
            self.features = features
        else:
            if _max_auto is None and _max_user is None:
                auto_tokens = None
            elif _max_auto and _max_user:
                auto_tokens = min(_max_auto, _max_user)
            else:
                auto_tokens = _max_auto or _max_user
            self.features = self._get_auto_features(
                code_file_manager, parser, model, features, auto_tokens
            )

        for f in self.features:
            code_message += f.get_code_message(self.config, code_file_manager, parser)
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

    def _get_auto_features(
        self,
        code_file_manager: "CodeFileManager",
        parser: "Parser",
        model: str,
        include_features: list[CodeFile],
        max_tokens: Optional[int] = None,
    ) -> list[CodeFile]:
        # Generate all possible permutations for all files in the project.
        candidate_features = list[CodeFile]()
        for path in get_non_gitignored_files(self.config.git_root):
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
        tokens_remaining = 1e6 if max_tokens is None else max_tokens

        def _calculate_feature_score(feature: CodeFile) -> float:
            score = 0.0
            tokens = feature.count_tokens(self.config, code_file_manager, parser, model)
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
        candidates_scored = [
            (f, _calculate_feature_score(f)) for f in candidate_features
        ]
        candidates_sorted = sorted(candidates_scored, key=lambda x: x[1], reverse=True)
        for feature, _ in candidates_sorted:
            feature_tokens = feature.count_tokens(
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
                    tokens_remaining += all_features[f_index].count_tokens(
                        self.config, code_file_manager, parser, model
                    )
                    all_features = all_features[:f_index] + all_features[f_index + 1 :]
            all_features.append(feature)
            tokens_remaining -= feature.count_tokens(
                self.config, code_file_manager, parser, model
            )

        def _feature_relative_path(f: CodeFile) -> str:
            return os.path.relpath(f.path, self.config.git_root)

        return sorted(all_features, key=_feature_relative_path)

    def include_file(self, code_file: CodeFile):
        if not os.path.exists(code_file.path):
            cprint(f"File does not exist: {code_file.path}\n", "red")
            return
        if code_file.path in self.settings.paths:
            cprint(f"File already in context: {code_file.path}\n", "yellow")
            return
        if code_file.path in self.settings.exclude_paths:
            self.settings.exclude_paths.remove(code_file.path)
        self.settings.paths.append(code_file.path)
        self._set_include_files()
        cprint(f"File included in context: {code_file.path}\n", "green")

    def exclude_file(self, code_file: CodeFile):
        if not os.path.exists(code_file.path):
            cprint(f"File does not exist: {code_file.path}\n", "red")
            return
        if code_file.path not in self.settings.paths:
            cprint(f"File not in context: {code_file.path}\n", "yellow")
            return
        if code_file.path in self.settings.exclude_paths:
            self.settings.paths.remove(code_file.path)
        self.settings.exclude_paths.append(code_file.path)
        self._set_include_files()
        cprint(f"File removed from context: {code_file.path}\n", "green")
