from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, TypedDict, Union

from ragdaemon.daemon import Daemon

from mentat.code_feature import CodeFeature, get_consolidated_feature_refs
from mentat.diff_context import DiffContext
from mentat.errors import PathValidationError
from mentat.git_handler import get_git_root_for_path
from mentat.include_files import (
    PathType,
    get_code_features_for_path,
    get_path_type,
    match_path_with_patterns,
    validate_and_format_path,
)
from mentat.interval import parse_intervals, split_intervals_from_path
from mentat.llm_api_handler import get_max_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream
from mentat.utils import get_relative_path, mentat_dir_path


class ContextStreamMessage(TypedDict):
    cwd: str
    diff_context_display: Optional[str]
    auto_context_tokens: int
    features: List[str]
    git_diff_paths: List[str]
    git_untracked_paths: List[str]
    total_tokens: int
    maximum_tokens: int
    total_cost: float


graphs_dir = mentat_dir_path / "ragdaemon"
graphs_dir.mkdir(parents=True, exist_ok=True)


class CodeContext:
    daemon: Daemon

    def __init__(
        self,
        stream: SessionStream,
        cwd: Path,
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        ignore_patterns: Iterable[Path | str] = [],
    ):
        self.diff = diff
        self.pr_diff = pr_diff
        self.ignore_patterns = set(Path(p) for p in ignore_patterns)

        self.diff_context = DiffContext(stream, cwd, self.diff, self.pr_diff)

        self.include_files: Dict[Path, List[CodeFeature]] = {}
        self.ignore_files: Set[Path] = set()

    async def refresh_daemon(self):
        """Call before interacting with context to ensure daemon is up to date."""

        if not hasattr(self, "daemon"):
            # Daemon is initialized after setup because it needs the embedding_provider.
            ctx = SESSION_CONTEXT.get()
            cwd = ctx.cwd
            llm_api_handler = ctx.llm_api_handler

            # Use print because stream is not initialized yet
            print("Scanning codebase for updates...")
            if not get_git_root_for_path(cwd, raise_error=False):
                print("\033[93mWarning: Not a git repository (this might take a while)\033[0m")

            annotators: dict[str, dict[str, Any]] = {
                "hierarchy": {"ignore_patterns": [str(p) for p in self.ignore_patterns]},
                "chunker_line": {"lines_per_chunk": 50},
                "diff": {"diff": self.diff_context.target},
            }
            self.daemon = Daemon(
                cwd=cwd,
                annotators=annotators,
                verbose=False,
                graph_path=graphs_dir / f"ragdaemon-{cwd.name}.json",
                spice_client=llm_api_handler.spice,
                model=ctx.config.embedding_model,
                provider=ctx.config.embedding_provider,
            )
        await self.daemon.update()

    async def refresh_context_display(self):
        """
        Sends a message to the client with the code context. It is called in the main loop.
        """
        ctx = SESSION_CONTEXT.get()

        diff_context_display = self.diff_context.get_display_context()

        features = get_consolidated_feature_refs(
            [feature for file_features in self.include_files.values() for feature in file_features]
        )
        git_diff_paths = [str(p) for p in self.diff_context.diff_files()]
        git_untracked_paths = [str(p) for p in self.diff_context.untracked_files()]

        total_tokens = await ctx.conversation.count_tokens(include_code_message=True)

        total_cost = ctx.llm_api_handler.spice.total_cost

        data = ContextStreamMessage(
            cwd=str(ctx.cwd),
            diff_context_display=diff_context_display,
            auto_context_tokens=ctx.config.auto_context_tokens,
            features=features,
            git_diff_paths=git_diff_paths,
            git_untracked_paths=git_untracked_paths,
            total_tokens=total_tokens,
            maximum_tokens=get_max_tokens(),
            total_cost=total_cost,
        )
        ctx.stream.send(data, channel="context_update")

    async def get_code_message(
        self,
        prompt_tokens: int,
        prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,  # for training/benchmarking
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
        llm_api_handler = session_context.llm_api_handler
        model = config.model
        cwd = session_context.cwd
        code_file_manager = session_context.code_file_manager

        # Setup the header (Mentat-specific, before ragdaemon context)
        header_lines = list[str]()
        self.diff_context.refresh()
        if self.diff_context.diff_files():
            header_lines += [f"Diff References: {self.diff_context.name}\n"]
        header_lines += ["Code Files:\n\n"]

        # Setup a ContextBuilder from Mentat's include_files / diff_context
        await self.refresh_daemon()
        context_builder = self.daemon.get_context("", max_tokens=0)
        diff_nodes: list[str] = [
            node
            for node, data in self.daemon.graph.nodes(data=True)  # pyright: ignore
            if data and "type" in data and data["type"] == "diff"
        ]
        if not self.include_files.values():
            for node in diff_nodes:
                context_builder.add_diff(node)
        for path, features in self.include_files.items():
            for feature in features:
                interval_string = feature.interval_string()
                if interval_string and "-" in interval_string:
                    start, exclusive_end = interval_string.split("-")
                    inclusive_end = str(int(exclusive_end) - 1)
                    interval_string = f"{start}-{inclusive_end}"
                ref = feature.rel_path(session_context.cwd) + interval_string
                context_builder.add_ref(ref, tags=["user-included"])
            relative_path = get_relative_path(path, cwd).as_posix()
            diffs_for_path = [node for node in diff_nodes if f":{relative_path}" in node]
            for diff in diffs_for_path:
                context_builder.add_diff(diff)

        # If auto-context, replace the context_builder with a new one
        if config.auto_context_tokens > 0 and prompt:
            meta_tokens = llm_api_handler.spice.count_tokens("\n".join(header_lines), model, is_message=True)

            include_files_message = context_builder.render()
            include_files_tokens = llm_api_handler.spice.count_tokens(include_files_message, model, is_message=False)

            tokens_used = prompt_tokens + meta_tokens + include_files_tokens
            auto_tokens = min(
                get_max_tokens() - tokens_used - config.token_buffer,
                config.auto_context_tokens,
            )
            context_builder = self.daemon.get_context(
                query=prompt,
                context_builder=context_builder,  # Pass include_files / diff_context to ragdaemon
                max_tokens=get_max_tokens(),
                auto_tokens=auto_tokens,
            )
            for ref in context_builder.to_refs():
                new_features = list[CodeFeature]()  # Save ragdaemon context back to include_files
                path, interval_str = split_intervals_from_path(Path(ref))
                if not interval_str:
                    new_features.append(CodeFeature(cwd / path))
                else:
                    intervals = parse_intervals(interval_str)
                    for interval in intervals:
                        new_features.append(CodeFeature(cwd / path, interval))
                self.include_features(new_features)

        # The context message is rendered by ragdaemon (ContextBuilder.render())
        context_message = context_builder.render()
        for relative_path in context_builder.context.keys():
            path = Path(cwd / relative_path).resolve()
            if path not in code_file_manager.file_lines:
                with open(path, "r") as file:  # Used by code_file_manager to validate file_edits
                    lines = file.read().split("\n")
                    code_file_manager.file_lines[path] = lines
        return "\n".join(header_lines) + context_message

    def get_all_features(
        self,
        max_chars: int = 100000,
        split_intervals: bool = True,
    ) -> list[CodeFeature]:
        """
        Retrieves every CodeFeature under the cwd. If files_only is True the features won't be split into intervals
        """
        session_context = SESSION_CONTEXT.get()
        cwd = session_context.cwd

        all_features = list[CodeFeature]()
        for _, data in self.daemon.graph.nodes(data=True):  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if data is None or "type" not in data or "ref" not in data or data["type"] not in {"file", "chunk"}:  # pyright: ignore[reportUnnecessaryComparison]
                continue
            path, interval = split_intervals_from_path(data["ref"])
            intervals = parse_intervals(interval)
            if not intervals:
                all_features.append(CodeFeature(cwd / path))
            for _interval in intervals:
                all_features.append(CodeFeature(cwd / path, _interval))
        return all_features

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
                    # Intervals can still overlap if user includes intervals different than what chunker breaks up,
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

    def include(self, path: Path | str, exclude_patterns: Iterable[Path | str] = []) -> Set[Path]:
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
            session_context.stream.send(f"Path {interval_path} not in context", style="error")
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
            validated_path = validate_and_format_path(path, session_context.cwd, check_for_text=False)
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
            pass

        return excluded_paths

    async def search(
        self,
        query: str,
        max_results: int | None = None,
    ) -> list[tuple[CodeFeature, float]]:
        """Return the top n features that are most similar to the query."""

        cwd = SESSION_CONTEXT.get().cwd
        all_nodes_sorted = self.daemon.search(query, max_results)
        all_features_sorted = list[tuple[CodeFeature, float]]()
        for node in all_nodes_sorted:
            if node.get("type") not in {"file", "chunk"}:
                continue
            distance = node["distance"]
            path, interval = split_intervals_from_path(Path(node["ref"]))
            if not interval:
                feature = CodeFeature(cwd / path)
                all_features_sorted.append((feature, distance))
            else:
                intervals = parse_intervals(interval)
                for _interval in intervals:
                    feature = CodeFeature(cwd / path, _interval)
                    all_features_sorted.append((feature, distance))
        if max_results is None:
            return all_features_sorted
        else:
            return all_features_sorted[:max_results]

    def to_simple_context_dict(self) -> dict[str, list[str]]:
        """Return a simple dictionary representation of the code context"""

        simple_dict: dict[str, list[str]] = {}
        for path, features in self.include_files.items():
            simple_dict[str(path.absolute())] = [str(feature) for feature in features]
        return simple_dict

    def from_simple_context_dict(self, simple_dict: dict[str, list[str]]):
        """Load the code context from a simple dictionary representation"""

        for path_str, features_str in simple_dict.items():
            path = Path(path_str)
            features_for_path: List[CodeFeature] = []

            for feature_str in features_str:
                feature_path = Path(feature_str)

                # feature_path is already absolute, so cwd doesn't matter
                current_features = get_code_features_for_path(feature_path, cwd=Path("/"))
                features_for_path += list(current_features)

            self.include_files[path] = features_for_path
