from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Union

from mentat.code_feature import (
    CodeFeature,
    get_code_message_from_features,
    get_consolidated_feature_refs,
    split_file_into_intervals,
)
from mentat.diff_context import DiffContext
from mentat.errors import PathValidationError
from mentat.feature_filters.default_filter import DefaultFilter
from mentat.feature_filters.embedding_similarity_filter import EmbeddingSimilarityFilter
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
from mentat.interval import parse_intervals, split_intervals_from_path
from mentat.llm_api_handler import (
    count_tokens,
    get_max_tokens,
    raise_if_context_exceeds_max,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream


class CodeContext:
    def __init__(
        self,
        stream: SessionStream,
        git_root: Optional[Path] = None,
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        ignore_patterns: Iterable[Path | str] = [],
    ):
        self.git_root = git_root
        self.diff = diff
        self.pr_diff = pr_diff
        self.ignore_patterns = set(Path(p) for p in ignore_patterns)

        self.diff_context = None
        if self.git_root:
            self.diff_context = DiffContext(
                stream, self.git_root, self.diff, self.pr_diff
            )

        self.include_files: Dict[Path, List[CodeFeature]] = {}
        self.ignore_files: Set[Path] = set()
        self.auto_features: List[CodeFeature] = []

    def display_context(self):
        """Display the baseline context: included files and auto-context settings"""
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config

        stream.send("Code Context:", style="code")
        prefix = "  "
        stream.send(f"{prefix}Directory: {session_context.cwd}")
        if self.diff_context and self.diff_context.name:
            stream.send(f"{prefix}Diff:", end=" ")
            stream.send(self.diff_context.get_display_context(), style="success")

        if config.auto_context_tokens > 0:
            stream.send(f"{prefix}Auto-Context: Enabled")
            stream.send(f"{prefix}Auto-Context Tokens: {config.auto_context_tokens}")
        else:
            stream.send(f"{prefix}Auto-Context: Disabled")

        if self.include_files:
            stream.send(f"{prefix}Included files:")
            stream.send(f"{prefix + prefix}{session_context.cwd.name}")
            features = [
                feature
                for file_features in self.include_files.values()
                for feature in file_features
            ]
            refs = get_consolidated_feature_refs(features)
            print_path_tree(
                build_path_tree([Path(r) for r in refs], session_context.cwd),
                get_paths_with_git_diffs(self.git_root) if self.git_root else set(),
                session_context.cwd,
                prefix + prefix,
            )
        else:
            stream.send(f"{prefix}Included files: ", end="")
            stream.send("None", style="warning")

        if self.auto_features:
            stream.send(f"{prefix}Auto-Included Features:")
            refs = get_consolidated_feature_refs(self.auto_features)
            print_path_tree(
                build_path_tree([Path(r) for r in refs], session_context.cwd),
                get_paths_with_git_diffs(self.git_root) if self.git_root else set(),
                session_context.cwd,
                prefix + prefix,
            )

    async def get_code_message(
        self,
        prompt_tokens: int,
        prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,  # for training/benchmarking
        loading_multiplier: float = 0.0,
        suppress_context_check: bool = False,
    ) -> str:
        """
        Retrieves the current code message.
        'prompt' argument is embedded and used to search for similar files when auto-context is enabled.
        If prompt is empty, auto context won't be used.
        'prompt_tokens' argument is the total number of tokens used by the prompt before the code message,
        used to ensure that the code message won't overflow the model's context size
        """
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        model = config.model

        # Setup code message metadata
        code_message = list[str]()
        if self.diff_context:
            self.diff_context.clear_cache()
            if self.diff_context.diff_files():
                code_message += [
                    "Diff References:",
                    f' "-" = {self.diff_context.name}',
                    ' "+" = Active Changes',
                    "",
                ]

        code_message += ["Code Files:\n"]
        meta_tokens = count_tokens("\n".join(code_message), model, full_message=True)

        # Calculate user included features token size
        include_features = [
            feature
            for file_features in self.include_files.values()
            for feature in file_features
        ]
        include_files_message = get_code_message_from_features(include_features)
        include_files_tokens = count_tokens(
            "\n".join(include_files_message), model, full_message=False
        )

        tokens_used = prompt_tokens + meta_tokens + include_files_tokens
        if not suppress_context_check:
            raise_if_context_exceeds_max(tokens_used)
        auto_tokens = min(
            get_max_tokens() - tokens_used - config.token_buffer,
            config.auto_context_tokens,
        )

        # Get auto included features
        if config.auto_context_tokens > 0 and prompt:
            features = self.get_all_features()
            feature_filter = DefaultFilter(
                auto_tokens,
                prompt,
                expected_edits,
                loading_multiplier=loading_multiplier,
            )
            self.auto_features = list(
                set(self.auto_features) | set(await feature_filter.filter(features))
            )

        # Merge include file features and auto features and add to code message
        code_message += get_code_message_from_features(
            include_features + self.auto_features
        )

        return "\n".join(code_message)

    def get_all_features(
        self,
        max_chars: int = 100000,
        split_intervals: bool = True,
    ) -> list[CodeFeature]:
        """
        Retrieves every CodeFeature under the cwd. If files_only is True the features won't be split into intervals
        """
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

            if not split_intervals:
                _feature = CodeFeature(path)
                all_features.append(_feature)
            else:
                full_feature = CodeFeature(path)
                _split_features = split_file_into_intervals(full_feature)
                all_features += _split_features

        return sorted(all_features, key=lambda f: f.path)

    def clear_auto_context(self):
        """
        Clears all auto-features added to the conversation so far.
        """
        self.auto_features = []

    def include_features(self, code_features: Iterable[CodeFeature]):
        """
        Adds the given code features to context. If the feature is already included, it will not be added.
        """
        included_paths: Set[Path] = set()
        for code_feature in code_features:
            if code_feature.path not in self.include_files:
                self.include_files[code_feature.path] = [code_feature]
                included_paths.add(Path(str(code_feature)))
            else:
                code_feature_not_included = True
                for included_code_feature in self.include_files[code_feature.path]:
                    # Intervals can still overlap if user includes intervals different than what ctags breaks up,
                    # but we merge when making code message and don't duplicate lines
                    if (
                        included_code_feature.interval == code_feature.interval
                        # No need to include an interval if the entire file is already included
                        or included_code_feature.interval.whole_file()
                    ):
                        code_feature_not_included = False
                        break
                if code_feature_not_included:
                    if code_feature.interval.whole_file():
                        self.include_files[code_feature.path] = []
                    self.include_files[code_feature.path].append(code_feature)
                    included_paths.add(Path(str(code_feature)))
        return included_paths

    def include(
        self, path: Path | str, exclude_patterns: Iterable[Path | str] = []
    ) -> Set[Path]:
        """
        Add paths to the context

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

        try:
            code_features = get_code_features_for_path(
                path=path,
                cwd=session_context.cwd,
                exclude_patterns=abs_exclude_patterns,
            )
        except PathValidationError as e:
            session_context.stream.send(str(e), style="error")
            return set()

        return self.include_features(code_features)

    def _exclude_file(self, path: Path) -> Path | None:
        session_context = SESSION_CONTEXT.get()
        if path in self.include_files:
            del self.include_files[path]
            return path
        else:
            session_context.stream.send(f"Path {path} not in context", style="error")

    def _exclude_file_interval(self, path: Path) -> Set[Path]:
        session_context = SESSION_CONTEXT.get()

        excluded_paths: Set[Path] = set()

        interval_path, interval_str = split_intervals_from_path(path)
        if interval_path not in self.include_files:
            session_context.stream.send(
                f"Path {interval_path} not in context", style="error"
            )
            return excluded_paths

        intervals = parse_intervals(interval_str)
        included_code_features: List[CodeFeature] = []
        for code_feature in self.include_files[interval_path]:
            if code_feature.interval not in intervals:
                included_code_features.append(code_feature)
            else:
                excluded_paths.add(Path(str(code_feature)))

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
            session_context.stream.send(str(e), style="error")

        return excluded_paths

    async def search(
        self,
        query: str,
        max_results: int | None = None,
    ) -> list[tuple[CodeFeature, float]]:
        """Return the top n features that are most similar to the query."""

        all_features = self.get_all_features()

        embedding_similarity_filter = EmbeddingSimilarityFilter(query)
        all_features_sorted = await embedding_similarity_filter.score(all_features)
        if max_results is None:
            return all_features_sorted
        else:
            return all_features_sorted[:max_results]
