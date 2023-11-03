from __future__ import annotations
from ipdb import set_trace

import os
from pathlib import Path
from textwrap import dedent
from typing import Dict, Iterable, List, Optional, Set, Tuple

from mentat.code_feature import (
    CodeFeature,
    CodeMessageLevel,
    count_feature_tokens,
    split_file_into_intervals,
)
from mentat.code_map import check_ctags_disabled
from mentat.diff_context import DiffContext
from mentat.embeddings import get_feature_similarity_scores
from mentat.git_handler import get_non_gitignored_files, get_paths_with_git_diffs
from mentat.include_files import (
    PathValidationException,
    build_path_tree,
    get_code_features_for_path,
    get_paths_for_directory,
    is_file_text_encoded,
    match_path_with_patterns,
    print_path_tree,
)
from mentat.llm_api import count_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream
from mentat.utils import sha256


def _get_all_features(
    root: Path,
    include_files: Dict[Path, CodeFeature],
    ignore_paths: Set[Path],
    diff_context: DiffContext,
    code_map: bool,
    level: CodeMessageLevel,
) -> List[CodeFeature]:
    """Return a list of all features in the git root with given properties."""
    all_features: List[CodeFeature] = []
    for path in get_paths_for_directory(root, ignore_patterns=ignore_paths):
        diff_target = diff_context.target if path in diff_context.files else None
        user_included = path in include_files
        if level == CodeMessageLevel.INTERVAL:
            # Return intervals if code_map is enabled, otherwise return the full file
            full_feature = CodeFeature(
                path,
                level=CodeMessageLevel.CODE,
                diff=diff_target,
                user_included=user_included,
            )
            if not code_map:
                all_features.append(full_feature)
            else:
                _split_features = split_file_into_intervals(
                    path,
                    full_feature,
                    user_features=[f for f in include_files.values() if f.path == path],
                )
                all_features += _split_features
        else:
            _feature = CodeFeature(path, level=level, diff=diff_target, user_included=user_included)
            all_features.append(_feature)

    return all_features


class CodeContext:
    def __init__(
        self,
        stream: SessionStream,
        git_root: Path,
        diff: str | None = None,
        pr_diff: str | None = None,
        ignore_patterns: Iterable[str | Path] = [],
    ):
        self.diff = diff
        self.pr_diff = pr_diff

        self.diff_context = DiffContext(stream, git_root, self.diff, self.pr_diff)
        # TODO: This is a dict so we can quickly reference either a path (key)
        # or the CodeFeature (value) and its interval. Redundant.
        self.include_files: Dict[Path, CodeFeature] = dict()
        self.ignore_patterns: Set[str | Path] = set(ignore_patterns)
        self.features: List[CodeFeature] = list()
        self.code_map = True

    def set_code_map(self):
        ctx = SESSION_CONTEXT.get()

        if ctx.config.no_code_map:
            self.code_map = False
        else:
            disabled_reason = check_ctags_disabled()
            if disabled_reason:
                ctags_disabled_message = f"""
                    There was an error with your universal ctags installation, disabling CodeMap.
                    Reason: {disabled_reason}
                """
                ctags_disabled_message = dedent(ctags_disabled_message)
                ctx.stream.send(ctags_disabled_message, color="yellow")
                ctx.config.no_code_map = True
                self.code_map = False
            else:
                self.code_map = True

    def display_context(self):
        """Display the baseline context: included files and auto-context settings"""
        ctx = SESSION_CONTEXT.get()

        ctx.stream.send("Code Context:", color="blue")
        prefix = "  "
        ctx.stream.send(f"{prefix}Directory: {ctx.cwd}")
        if self.diff_context.name:
            ctx.stream.send(f"{prefix}Diff:", end=" ")
            ctx.stream.send(self.diff_context.get_display_context(), color="green")
        if self.include_files:
            ctx.stream.send(f"{prefix}Included files:")
            ctx.stream.send(f"{prefix + prefix}{ctx.cwd.name}")
            print_path_tree(
                build_path_tree(list(self.include_files.values()), git_root),
                get_paths_with_git_diffs(),
                git_root,
                prefix + prefix,
            )
        else:
            ctx.stream.send(f"{prefix}Included files: None", color="yellow")
        auto = ctx.config.auto_tokens
        if auto != 0:
            ctx.stream.send(f"{prefix}Auto-token limit:" f" {'Model max (default)' if auto is None else auto}")
            ctx.stream.send(f"{prefix}CodeMaps: {'Enabled' if self.code_map else 'Disabled'}")

    def display_features(self):
        """Display a summary of all active features"""
        ctx = SESSION_CONTEXT.get()

        auto_features = {level: 0 for level in CodeMessageLevel}
        for f in self.features:
            if f.path not in self.include_files:
                auto_features[f.level] += 1
        if any(auto_features.values()):
            ctx.stream.send("Auto-Selected Features:", color="blue")
            for level, count in auto_features.items():
                if count:
                    ctx.stream.send(f"  {count} {level.description}")

    _code_message: str | None = None
    _code_message_checksum: str | None = None

    def _get_code_message_checksum(self, max_tokens: Optional[int] = None) -> str:
        ctx = SESSION_CONTEXT.get()

        if not self.features:
            features_checksum = ""
        else:
            feature_files = set(f.path for f in self.features)
            feature_file_checksums = [ctx.code_file_manager.get_file_checksum(f) for f in feature_files]
            features_checksum = sha256("".join(feature_file_checksums))
        settings = {
            "code_map": self.code_map,
            "auto_tokens": ctx.config.auto_tokens,
            "use_embeddings": ctx.config.use_embeddings,
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
        model: str,
        max_tokens: int,
    ) -> str:
        code_message_checksum = self._get_code_message_checksum(max_tokens)
        if self._code_message is None or code_message_checksum != self._code_message_checksum:
            self._code_message = await self._get_code_message(prompt, model, max_tokens)
            self._code_message_checksum = self._get_code_message_checksum(max_tokens)
        return self._code_message

    async def _get_code_message(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> str:
        ctx = SESSION_CONTEXT.get()

        code_message: List[str] = []

        self.diff_context.clear_cache()
        self.set_code_map()
        if self.diff_context.files:
            code_message += [
                "Diff References:",
                f' "-" = {self.diff_context.name}',
                ' "+" = Active Changes',
                "",
            ]
        code_message += ["Code Files:\n"]
        features = self._get_include_features()
        meta_tokens = count_tokens("\n".join(code_message), model)  # NOTE: why does this take so long to run?
        include_feature_tokens = sum(await count_feature_tokens(features, model))
        _max_auto = max(0, max_tokens - meta_tokens - include_feature_tokens)
        _max_user = ctx.config.auto_tokens
        self.features = features

        # NOTE: disabled aut features (for now)
        # if _max_auto == 0 or _max_user == 0:
        #     self.features = features
        # else:
        #     auto_tokens = _max_auto if _max_user is None else min(_max_auto, _max_user)
        #     self.features = await self._get_auto_features(prompt, model, features, auto_tokens)

        for f in self.features:
            code_message += f.get_code_message()
        return "\n".join(code_message)

    def _get_include_features(self) -> list[CodeFeature]:
        ctx = SESSION_CONTEXT.get()

        include_features: List[CodeFeature] = []
        for path, feature in self.include_files.items():
            annotations = self.diff_context.get_annotations(path)
            has_diff = any(a.intersects(i) for a in annotations for i in feature.intervals)
            feature = CodeFeature(
                feature.ref(),
                feature.level,
                diff=self.diff_context.target if has_diff else None,
                user_included=True,
            )
            include_features.append(feature)

        def _feature_relative_path(f: CodeFeature) -> str:
            return os.path.relpath(f.path, ctx.cwd)

        return sorted(include_features, key=_feature_relative_path)

    async def _get_auto_features(
        self,
        prompt: str,
        model: str,
        include_features: list[CodeFeature],
        max_tokens: int,
    ) -> List[CodeFeature]:
        """Return a list of features that fit within the max_tokens limit

        - user_features: excluded from auto-features process, added to return list
        """
        ctx = SESSION_CONTEXT.get()

        # Find the first (longest) level that fits
        include_features_tokens = sum(await count_feature_tokens(include_features, model))
        max_auto_tokens = max_tokens - include_features_tokens
        all_features = include_features.copy()
        levels = [CodeMessageLevel.FILE_NAME]
        if not ctx.config.no_code_map:
            levels = [CodeMessageLevel.CMAP_FULL, CodeMessageLevel.CMAP] + levels
        for level in levels:
            level_features = _get_all_features(
                git_root,
                self.include_files,
                self.ignore_patterns,
                self.diff_context,
                self.code_map,
                level,
            )
            level_features = [f for f in level_features if f.path not in self.include_files]
            level_length = sum(await count_feature_tokens(level_features, model))
            if level_length < max_auto_tokens:
                all_features += level_features
                break

        # Sort by relative path
        def _feature_relative_path(f: CodeFeature) -> str:
            return os.path.relpath(f.path, git_root)

        all_features = sorted(all_features, key=_feature_relative_path)

        # If there's room, convert cmap features to code features (full text)
        # starting with the highest-scoring.
        cmap_features_tokens = sum(await count_feature_tokens(all_features, model))
        max_sim_tokens = max_tokens - cmap_features_tokens
        if config.auto_tokens is not None:
            max_sim_tokens = min(max_sim_tokens, config.auto_tokens)

        if config.use_embeddings and max_sim_tokens > 0 and prompt != "":
            sim_tokens = 0

            # Get embedding-similarity scores for all files
            all_code_features_sorted = await self.search(
                query=prompt,
                level=CodeMessageLevel.CODE,
                # TODO: Change to INTERVAL after update get_code_message
            )
            for code_feature, _ in all_code_features_sorted:
                abs_path = git_root / code_feature.path
                # Calculate the total change in length
                i_cmap, cmap_feature = next((i, f) for i, f in enumerate(all_features) if f.path == abs_path)
                recovered_tokens = cmap_feature.count_tokens(model)
                new_tokens = code_feature.count_tokens(model)
                forecast = max_sim_tokens - sim_tokens + recovered_tokens - new_tokens
                if forecast > 0:
                    sim_tokens = sim_tokens + new_tokens - recovered_tokens
                    all_features[i_cmap] = code_feature

        return sorted(all_features, key=_feature_relative_path)

    def include(self, path: Path, ignore_patterns: Iterable[Path | str] = []) -> Set[Path]:
        """Add code to the context

        '.' is replaced with '*' (recusively search the cwd)

        Args:
            `path`: can be a relative or absolute file path, file interval path, directory, or glob pattern.
            TODO: allow `str` and `Path`?

        Return:
            A set of paths that have been successfully added to the context
        """
        ctx = SESSION_CONTEXT.get()

        if str(path) == ".":
            path = Path("*")

        included_paths: Set[Path] = set()
        try:
            code_features = get_code_features_for_path(
                path=path,
                cwd=ctx.cwd,
                ignore_patterns=[*ignore_patterns, *self.ignore_patterns, *ctx.config.file_exclude_glob_list],
            )
        except PathValidationException as e:
            ctx.stream.send(e, color="light_red")
            return included_paths

        for code_feature in code_features:
            self.include_files[code_feature.path] = code_feature
            included_paths.add(code_feature.path)

        return included_paths

    def exclude(self, path: Path) -> Set[Path]:
        """Remove code from the context

        Args:
            `path`: can be a relative or absolute file path, file interval path, directory, or glob pattern.

        Return:
            A set of paths that have been successfully removed from the context
        """
        ctx = SESSION_CONTEXT.get()

        excluded_paths: Set[Path] = set()
        try:
            # file
            if path.is_file():
                if path not in self.include_files:
                    ctx.stream.send(f"Path {path} not in context", color="light_red")
                    return excluded_paths
                excluded_paths.add(path)
                del self.include_files[path]
            # file interval
            elif ":" in str(path):
                _interval_path, _ = str(path).split(":", 1)
                interval_path = Path(_interval_path)
                if interval_path not in self.include_files:
                    ctx.stream.send(f"Path {path} not in context", color="light_red")
                    return excluded_paths
                excluded_paths.add(interval_path)
                del self.include_files[interval_path]
            # TODO: directory
            elif path.is_dir():
                raise NotImplementedError()
            # glob
            else:
                for included_path in self.include_files.keys():
                    if match_path_with_patterns(included_path, set(str(path))):
                        excluded_paths.add(included_path)
                        del self.include_files[included_path]

        except PathValidationException as e:
            ctx.stream.send(e, color="light_red")
            return excluded_paths

        return excluded_paths

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        level: CodeMessageLevel = CodeMessageLevel.INTERVAL,
    ) -> List[Tuple[CodeFeature, float]]:
        """Return the top n features that are most similar to the query."""
        ctx = SESSION_CONTEXT.get()

        if not ctx.config.use_embeddings:
            ctx.stream.send(
                "Embeddings are disabled. Enable with `/config use_embeddings true`",
                color="light_red",
            )
            return []

        all_features = _get_all_features(
            ctx.cwd,
            self.include_files,
            self.ignore_patterns,
            self.diff_context,
            self.code_map,
            level,
        )
        sim_scores = await get_feature_similarity_scores(query, all_features)
        all_features_scored = zip(all_features, sim_scores)
        all_features_sorted = sorted(all_features_scored, key=lambda x: x[1], reverse=True)
        if max_results is None:
            return all_features_sorted
        else:
            return all_features_sorted[:max_results]
