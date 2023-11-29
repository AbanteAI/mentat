from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from mentat.code_feature import (
    CodeFeature,
    CodeMessageLevel,
    get_code_message_from_features,
    split_file_into_intervals,
)
from mentat.code_map import check_ctags_disabled
from mentat.diff_context import DiffContext
from mentat.errors import PathValidationError
from mentat.feature_filters.default_filter import DefaultFilter
from mentat.feature_filters.embedding_similarity_filter import EmbeddingSimilarityFilter
from mentat.git_handler import get_paths_with_git_diffs
from mentat.include_files import (
    build_path_tree,
    get_code_features_for_path,
    get_paths_for_directory,
    is_file_text_encoded,
    match_path_with_patterns,
    print_path_tree,
    validate_and_format_path,
)
from mentat.interval import parse_intervals
from mentat.llm_api import count_tokens
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
        exclude_patterns: Iterable[Path | str] = [],
    ):
        self.diff = diff
        self.pr_diff = pr_diff
        self.exclude_patterns = set(Path(p) for p in exclude_patterns)

        self.diff_context = None
        if git_root:
            self.diff_context = DiffContext(stream, git_root, self.diff, self.pr_diff)

        # TODO: This is a dict so we can quickly reference either a path (key)
        # or the CodeFeatures (value) and their intervals. Redundant.
        # NOTE: this should be a set of CodeFeatures, not a list
        self.include_files: Dict[Path, List[CodeFeature]] = {}
        self.features: List[CodeFeature] = []
        self.ctags_disabled = check_ctags_disabled()

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
            stream.send(f"{prefix}Auto-Context: Enabled", color="green")
            if self.ctags_disabled:
                stream.send(
                    f"{prefix}Code Maps Disbled: {self.ctags_disabled}",
                    color="yellow",
                )
        else:
            stream.send(f"{prefix}Auto-Context: Disabled")

    def display_features(self):
        """Display a summary of all active features"""
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        auto_features = {level: 0 for level in CodeMessageLevel}
        for f in self.features:
            if f.path not in self.include_files:
                auto_features[f.level] += 1
        if any(auto_features.values()):
            stream.send("Auto-Selected Features:", color="blue")
            for level, count in auto_features.items():
                if count:
                    stream.send(f"  {count} {level.description}")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    def _get_code_message_checksum(
        self, prompt: str = "", max_tokens: Optional[int] = None
    ) -> str:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        code_file_manager = session_context.code_file_manager

        if not self.features:
            features_checksum = ""
        else:
            feature_files = {session_context.cwd / f.path for f in self.features}
            feature_file_checksums = [
                code_file_manager.get_file_checksum(f) for f in feature_files
            ]
            features_checksum = sha256("".join(feature_file_checksums))
        settings = {
            "prompt": prompt,
            "code_map_disabled": self.ctags_disabled,
            "auto_context": config.auto_context,
            "use_llm": self.use_llm,
            "diff": self.diff,
            "pr_diff": self.pr_diff,
            "max_tokens": max_tokens,
            "include_files": self.include_files,
        }
        settings_checksum = sha256(str(settings))
        return features_checksum + settings_checksum

    async def get_code_message(
        self,
        prompt: str,
        max_tokens: int,
        expected_edits: Optional[list[str]] = None,  # for training/benchmarking
    ) -> str:
        code_message_checksum = self._get_code_message_checksum(prompt, max_tokens)
        if (
            self._code_message is None
            or code_message_checksum != self._code_message_checksum
        ):
            self._code_message = await self._get_code_message(
                prompt, max_tokens, expected_edits
            )
            self._code_message_checksum = self._get_code_message_checksum(
                prompt, max_tokens
            )
        return self._code_message

    use_llm: bool = True

    async def _get_code_message(
        self,
        prompt: str,
        max_tokens: int,
        expected_edits: Optional[list[str]] = None,
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

                if len(self.include_files) == 0:
                    for file in self.diff_context.files:
                        self.include(file)

        code_message += ["Code Files:\n"]
        meta_tokens = count_tokens("\n".join(code_message), model)
        remaining_tokens = max_tokens - meta_tokens

        if not config.auto_context or remaining_tokens <= 0:
            self.features = self._get_include_features()
        else:
            self.features = self._get_all_features(
                CodeMessageLevel.INTERVAL,
            )
            feature_filter = DefaultFilter(
                remaining_tokens,
                model,
                not (bool(self.ctags_disabled)),
                self.use_llm,
                prompt,
                expected_edits,
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

    def _get_all_features(
        self,
        level: CodeMessageLevel,
        max_chars: int = 100000,
    ) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()

        all_features: List[CodeFeature] = []
        for path in get_paths_for_directory(
            path=session_context.cwd,
            exclude_patterns=[
                *self.exclude_patterns,
                *session_context.config.file_exclude_glob_list,
            ],
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
                # Return intervals if code_map is enabled, otherwise return the full file
                full_feature = CodeFeature(
                    path,
                    level=CodeMessageLevel.CODE,
                    diff=diff_target,
                    user_included=user_included,
                )
                if self.ctags_disabled:
                    all_features.append(full_feature)
                else:
                    _split_features = split_file_into_intervals(
                        full_feature, user_features=self.include_files.get(path, [])
                    )
                    all_features += _split_features
            else:
                _feature = CodeFeature(
                    path, level=level, diff=diff_target, user_included=user_included
                )
                all_features.append(_feature)

        return sorted(all_features, key=lambda f: f.path)

    def include(
        self, path: Path | str, exclude_patterns: Iterable[Path | str] = []
    ) -> Set[Path]:
        """Add code to the context

        Args:
            `path`: can be a relative or absolute file path, file interval path, directory, or glob pattern.

        Return:
            A set of paths that have been successfully added to the context
        """
        session_context = SESSION_CONTEXT.get()

        path = Path(path)

        included_paths: Set[Path] = set()
        try:
            code_features = get_code_features_for_path(
                path=path,
                cwd=session_context.cwd,
                exclude_patterns=[
                    *exclude_patterns,
                    *self.exclude_patterns,
                    *session_context.config.file_exclude_glob_list,
                ],
            )
        except PathValidationError as e:
            session_context.stream.send(e, color="light_red")
            return included_paths

        for code_feature in code_features:
            if code_feature.path in self.include_files:
                self.include_files[code_feature.path].append(code_feature)
            else:
                self.include_files[code_feature.path] = [code_feature]

        return included_paths

    def exclude(self, path: Path | str) -> Set[Path]:
        """Remove code from the context

        # NOTE: should this be the intended behavior?
        Code Features are removed from the context and are excluded from any future `include` calls (unless explicity specified).
        For paths that are files or file intervals, if they don't already exist in the Code Context an Exception is thrown.
        For file intervals, if the interval doesn't *exactly match* any intervals in the code context, nothing is removed.

        Args:
            `path`: can be a relative or absolute file path, file interval path, directory, or glob pattern.

        Return:
            A set of paths that have been successfully removed from the context
        """
        session_context = SESSION_CONTEXT.get()

        path = Path(path)

        excluded_paths: Set[Path] = set()

        try:
            validated_path = validate_and_format_path(
                path, session_context.cwd, check_for_text=False
            )
            # file
            if validated_path.is_file():
                if validated_path not in self.include_files:
                    session_context.stream.send(
                        f"Path {validated_path} not in context", color="light_red"
                    )
                    return excluded_paths
                excluded_paths.add(validated_path)
                del self.include_files[validated_path]
            # file interval
            elif len(str(validated_path).rsplit(":", 1)) > 1:
                interval_path, interval_str = str(validated_path).rsplit(":", 1)
                interval_path = Path(interval_path)
                if interval_path not in self.include_files:
                    session_context.stream.send(
                        f"Path {interval_path} not in context", color="light_red"
                    )
                    return excluded_paths
                intervals = parse_intervals(interval_str)
                included_code_features: List[CodeFeature] = []
                for code_feature in self.include_files[interval_path]:
                    if code_feature.interval in intervals:
                        excluded_path = f"{interval_path}:{code_feature.interval.start}-{code_feature.interval.end}"
                        excluded_paths.add(Path(excluded_path))
                    else:
                        included_code_features.append(code_feature)
                self.include_files[interval_path] = included_code_features
            # directory
            elif validated_path.is_dir():
                if validated_path not in self.include_files:
                    session_context.stream.send(
                        f"Directory path {validated_path} not in context",
                        color="light_red",
                    )
                    return excluded_paths
                excluded_paths.add(validated_path)
                del self.include_files[validated_path]
            # glob
            else:
                for included_path in self.include_files.keys():
                    if match_path_with_patterns(
                        included_path, set(str(validated_path))
                    ):
                        excluded_paths.add(included_path)
                        del self.include_files[included_path]
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

        all_features = self._get_all_features(
            level,
        )

        embedding_similarity_filter = EmbeddingSimilarityFilter(query)
        all_features_sorted = await embedding_similarity_filter.score(all_features)
        if max_results is None:
            return all_features_sorted
        else:
            return all_features_sorted[:max_results]
