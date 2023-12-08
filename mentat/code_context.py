from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Union

from mentat.code_feature import (
    CodeFeature,
    CodeMessageLevel,
    get_code_message_from_features,
    get_consolidated_feature_refs,
    split_file_into_intervals,
)
from mentat.diff_context import DiffContext
from mentat.errors import PathValidationError
from mentat.feature_filters.default_filter import DefaultFilter
from mentat.feature_filters.embedding_similarity_filter import EmbeddingSimilarityFilter
from mentat.feature_filters.truncate_filter import TruncateFilter
from mentat.git_handler import get_paths_with_git_diffs
from mentat.include_files import (
    PathType,
    build_path_tree,
    get_code_features_for_path,
    get_path_type,
    get_paths_for_directory,
    is_file_text_encoded,
    match_path_with_patterns,
    print_path_tree,
    validate_and_format_path,
)
from mentat.interval import parse_intervals
from mentat.llm_api_handler import count_tokens, is_test_environment
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream
from mentat.utils import sha256


class CodeContext:
    def __init__(
        self,
        stream: SessionStream,
        git_root: Optional[Path] = None,
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        ignore_patterns: Iterable[Path | str] = [],
    ):
        self.diff = diff
        self.pr_diff = pr_diff
        self.ignore_patterns = set(Path(p) for p in ignore_patterns)

        self.diff_context = None
        if git_root:
            self.diff_context = DiffContext(stream, git_root, self.diff, self.pr_diff)

        # TODO: This is a dict so we can quickly reference either a path (key)
        # or the CodeFeatures (value) and their intervals. Redundant.
        self.include_files: Dict[Path, List[CodeFeature]] = {}
        self.ignore_files: Set[Path] = set()
        self.features: List[CodeFeature] = []
        self.include_files: Dict[Path, List[CodeFeature]] = {}
        self.ignore_files: Set[Path] = set()
        self.features: List[CodeFeature] = []

    def display_context(self):
        """Display the baseline context: included files and auto-context settings"""
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config

        stream.send("Code Context:", color="blue")
        prefix = "  "
        stream.send(f"{prefix}Directory: {session_context.cwd}")
        if self.diff_context and self.diff_context.name:
            stream.send(f"{prefix}Diff:", end=" ")
            stream.send(self.diff_context.get_display_context(), color="green")
        if self.include_files:
            stream.send(f"{prefix}Included files:")
            stream.send(f"{prefix + prefix}{session_context.cwd.name}")
            print_path_tree(
                build_path_tree(list(self.include_files.keys()), session_context.cwd),
                get_paths_with_git_diffs(),
                session_context.cwd,
                prefix + prefix,
            )
        else:
            stream.send(f"{prefix}Included files: None", color="yellow")
        if config.auto_context:
            stream.send(f"{prefix}Auto-Context: Enabled")
            stream.send(f"{prefix}Auto-Tokens: {config.auto_tokens}")
        else:
            stream.send(f"{prefix}Auto-Context: Disabled")

        features = None
        if self.features:
            stream.send(f"{prefix}Active Features:")
            features = self.features
        elif self.include_files:
            stream.send(f"{prefix}Included files:")
            features = [
                _feat for _file in self.include_files.values() for _feat in _file
            ]
        if features is not None:
            refs = get_consolidated_feature_refs(features)
            print_path_tree(
                build_path_tree([Path(r) for r in refs], session_context.cwd),
                get_paths_with_git_diffs(),
                session_context.cwd,
                prefix + prefix,
            )
        else:
            stream.send(f"{prefix}Included files: None", color="yellow")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    def _get_code_message_checksum(
        self, prompt: Optional[str] = None, max_tokens: Optional[int] = None
    ) -> str:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        code_file_manager = session_context.code_file_manager

        if not self.features:
            features_checksum = ""
        else:
            feature_files = {
                session_context.cwd / f.path
                for f in self.features
                if (session_context.cwd / f.path).exists()
            }
            feature_file_checksums = [
                code_file_manager.get_file_checksum(f) for f in feature_files
            ]
            features_checksum = sha256("".join(feature_file_checksums))
        settings = {
            "prompt": prompt or "",
            "auto_context": config.auto_context,
            "use_llm": self.use_llm,
            "diff": self.diff,
            "pr_diff": self.pr_diff,
            "max_tokens": max_tokens or "",
            "include_files": self.include_files,
        }
        settings_checksum = sha256(str(settings))
        return features_checksum + settings_checksum

    async def get_code_message(
        self,
        prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        expected_edits: Optional[list[str]] = None,  # for training/benchmarking
        loading_multiplier: float = 0.0,
    ) -> str:
        code_message_checksum = self._get_code_message_checksum(prompt, max_tokens)
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = await self._get_code_message(
                prompt, max_tokens, expected_edits, loading_multiplier
            )
            self._code_message_checksum = self._get_code_message_checksum(
                prompt, max_tokens
            )
        return self._code_message

    use_llm: bool = False

    async def _get_code_message(
        self,
        prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        expected_edits: Optional[list[str]] = None,
        loading_multiplier: float = 0.0,
    ) -> str:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        model = config.model

        # Setup code message metadata
        code_message = list[str]()
        if self.diff_context:
            self.diff_context.clear_cache()
            if self.diff_context.files:
                code_message += [
                    "Diff References:",
                    f' "-" = {self.diff_context.name}',
                    ' "+" = Active Changes',
                    "",
                ]

                if len(self.include_files) == 0 and (self.diff or self.pr_diff):
                    for file in self.diff_context.files:
                        self.include(file)

        code_message += ["Code Files:\n"]
        meta_tokens = count_tokens("\n".join(code_message), model, full_message=True)
        remaining_tokens = None if max_tokens is None else max_tokens - meta_tokens
        auto_tokens = (
            None
            if remaining_tokens is None
            else min(remaining_tokens, config.auto_tokens)
        )

        if remaining_tokens is not None and remaining_tokens <= 0:
            self.features = []
            return ""
        elif not config.auto_context:
            self.features = self._get_include_features()
            if remaining_tokens is not None:
                if prompt and not is_test_environment():
                    self.features = await EmbeddingSimilarityFilter(prompt).filter(
                        self.features
                    )
                if sum(f.count_tokens(model) for f in self.features) > remaining_tokens:
                    self.features = await TruncateFilter(
                        remaining_tokens, model, respect_user_include=False
                    ).filter(self.features)
        else:
            self.features = self.get_all_features(
                CodeMessageLevel.INTERVAL,
            )
            if auto_tokens:
                feature_filter = DefaultFilter(
                    auto_tokens,
                    self.use_llm,
                    prompt,
                    expected_edits,
                    loading_multiplier=loading_multiplier,
                )
                self.features = await feature_filter.filter(self.features)

        # Group intervals by file, separated by ellipses if there are gaps
        code_message += get_code_message_from_features(self.features)
        return "\n".join(code_message)

    def _get_include_features(self) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()

        include_features: List[CodeFeature] = []
        for path, features in self.include_files.items():
            annotations = []
            if self.diff_context:
                annotations = self.diff_context.get_annotations(path)

            for feature in features:
                diff = None
                if self.diff_context:
                    has_diff = any(a.intersects(feature.interval) for a in annotations)
                    diff = self.diff_context.target if has_diff else None

                feature = CodeFeature(
                    feature.ref(),
                    feature.level,
                    diff=diff,
                    user_included=True,
                )
                include_features.append(feature)

        def _feature_relative_path(f: CodeFeature) -> str:
            return os.path.relpath(f.path, session_context.cwd)

        return sorted(include_features, key=_feature_relative_path)

    def get_all_features(
        self,
        level: CodeMessageLevel,
        max_chars: int = 100000,
    ) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()

        abs_exclude_patterns: Set[Path] = set()
        for pattern in self.ignore_patterns.union(
            session_context.config.file_exclude_glob_list
        ):
            if not Path(pattern).is_absolute():
                abs_exclude_patterns.add(session_context.cwd / pattern)
            else:
                abs_exclude_patterns.add(Path(pattern))

        all_features: List[CodeFeature] = []
        for path in get_paths_for_directory(
            path=session_context.cwd, exclude_patterns=abs_exclude_patterns
        ):
            if not is_file_text_encoded(path) or os.path.getsize(path) > max_chars:
                continue

            diff_target = None
            if self.diff_context:
                diff_target = (
                    self.diff_context.target
                    if path in self.diff_context.files
                    else None
                )

            user_included = path in self.include_files

            if level == CodeMessageLevel.INTERVAL:
                full_feature = CodeFeature(
                    path,
                    level=CodeMessageLevel.CODE,
                    diff=diff_target,
                    user_included=user_included,
                )
                _split_features = split_file_into_intervals(
                    full_feature,
                    user_features=self.include_files.get(path, []),
                )
                all_features += _split_features
            else:
                _feature = CodeFeature(
                    path, level=level, diff=diff_target, user_included=user_included
                )
                all_features.append(_feature)

            # if level == CodeMessageLevel.INTERVAL:
            #     full_feature = CodeFeature(
            #         path,
            #         level=CodeMessageLevel.CODE,
            #         diff=diff_target,
            #         user_included=user_included,
            #     )
            #     if self.ctags_disabled:
            #         all_features.append(full_feature)
            #     else:
            #         _split_features = split_file_into_intervals(
            #             full_feature, user_features=self.include_files.get(path, [])
            #         )
            #         all_features += _split_features
            # else:
            #     _feature = CodeFeature(path, level=level, diff=diff_target, user_included=user_included)
            #     all_features.append(_feature)

        return sorted(all_features, key=lambda f: f.path)

    def include(
        self, path: Path | str, exclude_patterns: Iterable[Path | str] = []
    ) -> Set[Path]:
        """Add code to the context

        Paths that are already in the context and invalid paths are ignored.

        The following are behaviors for each `path` type:

        - File: the file is added to the context.
        - File interval: the file is added to the context, and the interval is added to the file
        - Directory: all files in the directory are recursively added to the context
        - Glob pattern: all files that match the glob pattern are added to the context

        Args:
            `path`: can be a relative or absolute file path, file interval path, directory, or glob pattern.

        Return:
            A set of paths that have been successfully included in the context
        """
        session_context = SESSION_CONTEXT.get()

        path = Path(path)

        abs_exclude_patterns: Set[Path] = set()
        all_exclude_patterns: Set[Union[str, Path]] = set(
            [
                *exclude_patterns,
                *self.ignore_patterns,
                *session_context.config.file_exclude_glob_list,
            ]
        )
        for pattern in all_exclude_patterns:
            if not Path(pattern).is_absolute():
                abs_exclude_patterns.add(session_context.cwd / pattern)
            else:
                abs_exclude_patterns.add(Path(pattern))

        included_paths: Set[Path] = set()
        try:
            code_features = get_code_features_for_path(
                path=path,
                cwd=session_context.cwd,
                exclude_patterns=abs_exclude_patterns,
            )
        except PathValidationError as e:
            session_context.stream.send(e, color="light_red")
            return included_paths

        for code_feature in code_features:
            # Path in included files
            if code_feature.path not in self.include_files:
                self.include_files[code_feature.path] = [code_feature]
                included_paths.add(Path(code_feature.ref()))
            # Path not in included files
            else:
                code_feature_not_included = True
                # NOTE: should have CodeFeatures in a hashtable
                for included_code_feature in self.include_files[code_feature.path]:
                    if included_code_feature.interval == code_feature.interval:
                        code_feature_not_included = False
                        break
                if code_feature_not_included:
                    self.include_files[code_feature.path].append(code_feature)
                    included_paths.add(Path(code_feature.ref()))

        return included_paths

    def _exclude_file(self, path: Path) -> Path | None:
        session_context = SESSION_CONTEXT.get()
        if path in self.include_files:
            del self.include_files[path]
            return path
        else:
            session_context.stream.send(
                f"Path {path} not in context", color="light_red"
            )

    def _exclude_file_interval(self, path: Path) -> Set[Path]:
        session_context = SESSION_CONTEXT.get()

        excluded_paths: Set[Path] = set()

        interval_path, interval_str = str(path).rsplit(":", 1)
        interval_path = Path(interval_path)
        if interval_path not in self.include_files:
            session_context.stream.send(
                f"Path {interval_path} not in context", color="light_red"
            )
            return excluded_paths

        intervals = parse_intervals(interval_str)
        included_code_features: List[CodeFeature] = []
        for code_feature in self.include_files[interval_path]:
            if code_feature.interval not in intervals:
                included_code_features.append(code_feature)
            else:
                excluded_paths.add(Path(code_feature.ref()))

        if len(included_code_features) == 0:
            del self.include_files[interval_path]
        else:
            self.include_files[interval_path] = included_code_features

        return excluded_paths

    def _exclude_directory(self, path: Path) -> Set[Path]:
        excluded_paths: Set[Path] = set()

        paths_to_exclude: Set[Path] = set()
        for included_path in self.include_files:
            if path in included_path.parents:
                paths_to_exclude.add(included_path)
        for excluded_path in paths_to_exclude:
            del self.include_files[excluded_path]
            excluded_paths.add(excluded_path)

        return excluded_paths

    def _exclude_glob(self, path: Path) -> Set[Path]:
        excluded_paths: Set[Path] = set()

        paths_to_exclude: Set[Path] = set()
        for included_path in self.include_files:
            if match_path_with_patterns(included_path, set([path])):
                paths_to_exclude.add(included_path)
        for excluded_path in paths_to_exclude:
            del self.include_files[excluded_path]
            excluded_paths.add(excluded_path)

        return excluded_paths

    def exclude(self, path: Path | str) -> Set[Path]:
        """Remove code from the context

        Paths that are not in the context and invalid paths are ignored.

        The following are behaviors for each `path` type:

        - File: the file is removed from the context
        - File interval: the interval is removed from the file. If the file doesn't have the exact interval specified,
          nothing is removed.
        - Directory: all files in the directory are removed from the context
        - Glob pattern: all files that match the glob pattern are removed from the context

        Args:
            `path`: can be a relative or absolute file path, file interval path, directory, or glob pattern.

        Return:
            A set of paths that have been successfully excluded from the context
        """
        session_context = SESSION_CONTEXT.get()

        path = Path(path)
        excluded_paths: Set[Path] = set()
        try:
            validated_path = validate_and_format_path(
                path, session_context.cwd, check_for_text=False
            )
            match get_path_type(validated_path):
                case PathType.FILE:
                    excluded_path = self._exclude_file(validated_path)
                    if excluded_path:
                        excluded_paths.add(excluded_path)
                case PathType.FILE_INTERVAL:
                    excluded_paths.update(self._exclude_file_interval(validated_path))
                case PathType.DIRECTORY:
                    excluded_paths.update(self._exclude_directory(validated_path))
                case PathType.GLOB:
                    excluded_paths.update(self._exclude_glob(validated_path))
        except PathValidationError as e:
            session_context.stream.send(e, color="light_red")

        return excluded_paths

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        level: CodeMessageLevel = CodeMessageLevel.INTERVAL,
    ) -> list[tuple[CodeFeature, float]]:
        """Return the top n features that are most similar to the query."""

        all_features = self.get_all_features(
            level,
        )

        embedding_similarity_filter = EmbeddingSimilarityFilter(query)
        all_features_sorted = await embedding_similarity_filter.score(all_features)
        if max_results is None:
            return all_features_sorted
        else:
            return all_features_sorted[:max_results]
