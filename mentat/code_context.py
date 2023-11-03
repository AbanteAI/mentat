from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent
from typing import Optional

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
    build_path_tree,
    get_ignore_files,
    get_include_files,
    is_file_text_encoded,
    print_invalid_path,
    print_path_tree,
)
from mentat.llm_api import count_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream
from mentat.utils import sha256


def _get_all_features(
    git_root: Path,
    include_files: dict[Path, CodeFeature],
    ignore_files: set[Path],
    diff_context: DiffContext,
    code_map: bool,
    level: CodeMessageLevel,
) -> list[CodeFeature]:
    """Return a list of all features in the git root with given properties."""

    all_features = list[CodeFeature]()
    for path in get_non_gitignored_files(git_root):
        abs_path = git_root / path
        if (
            abs_path.is_dir()
            or not is_file_text_encoded(abs_path)
            or abs_path in ignore_files
        ):
            continue

        diff_target = diff_context.target if abs_path in diff_context.files else None
        user_included = abs_path in include_files
        if level == CodeMessageLevel.INTERVAL:
            # Return intervals if code_map is enabled, otherwise return the full file
            full_feature = CodeFeature(
                abs_path,
                level=CodeMessageLevel.CODE,
                diff=diff_target,
                user_included=user_included,
            )
            if not code_map:
                all_features.append(full_feature)
            else:
                _split_features = split_file_into_intervals(
                    git_root,
                    full_feature,
                    user_features=[f for f in include_files.values() if f.path == path],
                )
                all_features += _split_features
        else:
            _feature = CodeFeature(
                abs_path, level=level, diff=diff_target, user_included=user_included
            )
            all_features.append(_feature)

    return all_features


class CodeContext:
    include_files: dict[Path, CodeFeature]
    ignore_files: set[Path]
    diff_context: DiffContext
    code_map: bool = True
    features: list[CodeFeature] = []
    diff: Optional[str] = None
    pr_diff: Optional[str] = None

    def __init__(
        self,
        stream: SessionStream,
        git_root: Path,
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
    ):
        self.diff = diff
        self.pr_diff = pr_diff
        self.diff_context = DiffContext(stream, git_root, self.diff, self.pr_diff)
        # TODO: This is a dict so we can quickly reference either a path (key)
        # or the CodeFeature (value) and its interval. Redundant.
        self.include_files = {}
        self.ignore_files = set()

    def set_paths(
        self,
        paths: list[Path],
        exclude_paths: list[Path],
        ignore_paths: list[Path] = [],
    ):
        if not paths and (self.diff or self.pr_diff) and self.diff_context.files:
            paths = self.diff_context.files
        self.include_files, invalid_paths = get_include_files(paths, exclude_paths)
        for invalid_path in invalid_paths:
            print_invalid_path(invalid_path)
        self.ignore_files = get_ignore_files(ignore_paths)

    def set_code_map(self):
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        stream = session_context.stream

        if config.no_code_map:
            self.code_map = False
        else:
            disabled_reason = check_ctags_disabled()
            if disabled_reason:
                ctags_disabled_message = f"""
                    There was an error with your universal ctags installation, disabling CodeMap.
                    Reason: {disabled_reason}
                """
                ctags_disabled_message = dedent(ctags_disabled_message)
                stream.send(ctags_disabled_message, color="yellow")
                config.no_code_map = True
                self.code_map = False
            else:
                self.code_map = True

    def display_context(self):
        """Display the baseline context: included files and auto-context settings"""
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        git_root = session_context.git_root

        stream.send("Code Context:", color="blue")
        prefix = "  "
        stream.send(f"{prefix}Directory: {git_root}")
        if self.diff_context.name:
            stream.send(f"{prefix}Diff:", end=" ")
            stream.send(self.diff_context.get_display_context(), color="green")
        if self.include_files:
            stream.send(f"{prefix}Included files:")
            stream.send(f"{prefix + prefix}{git_root.name}")
            print_path_tree(
                build_path_tree(list(self.include_files.values()), git_root),
                get_paths_with_git_diffs(),
                git_root,
                prefix + prefix,
            )
        else:
            stream.send(f"{prefix}Included files: None", color="yellow")
        auto = config.auto_tokens
        if auto != 0:
            stream.send(
                f"{prefix}Auto-token limit:"
                f" {'Model max (default)' if auto is None else auto}"
            )
            stream.send(
                f"{prefix}CodeMaps: {'Enabled' if self.code_map else 'Disabled'}"
            )

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

    def _get_code_message_checksum(self, max_tokens: Optional[int] = None) -> str:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        git_root = session_context.git_root
        code_file_manager = session_context.code_file_manager

        if not self.features:
            features_checksum = ""
        else:
            feature_files = {Path(git_root / f.path) for f in self.features}
            feature_file_checksums = [
                code_file_manager.get_file_checksum(f) for f in feature_files
            ]
            features_checksum = sha256("".join(feature_file_checksums))
        settings = {
            "code_map": self.code_map,
            "auto_tokens": config.auto_tokens,
            "use_embeddings": config.use_embeddings,
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
        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        code_message = list[str]()

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
        meta_tokens = count_tokens("\n".join(code_message), model)
        include_feature_tokens = sum(await count_feature_tokens(features, model))
        _max_auto = max(0, max_tokens - meta_tokens - include_feature_tokens)
        _max_user = config.auto_tokens
        if _max_auto == 0 or _max_user == 0:
            self.features = features
        else:
            auto_tokens = _max_auto if _max_user is None else min(_max_auto, _max_user)
            self.features = await self._get_auto_features(
                prompt, model, features, auto_tokens
            )

        for f in self.features:
            code_message += f.get_code_message()
        return "\n".join(code_message)

    def _get_include_features(self) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()
        git_root = session_context.git_root

        include_features = list[CodeFeature]()
        for path, feature in self.include_files.items():
            annotations = self.diff_context.get_annotations(path)
            has_diff = any(
                a.intersects(i) for a in annotations for i in feature.intervals
            )
            feature = CodeFeature(
                feature.ref(),
                feature.level,
                diff=self.diff_context.target if has_diff else None,
                user_included=True,
            )
            include_features.append(feature)

        def _feature_relative_path(f: CodeFeature) -> str:
            return os.path.relpath(f.path, git_root)

        return sorted(include_features, key=_feature_relative_path)

    async def _get_auto_features(
        self,
        prompt: str,
        model: str,
        include_features: list[CodeFeature],
        max_tokens: int,
    ) -> list[CodeFeature]:
        """Return a list of features that fit within the max_tokens limit

        - user_features: excluded from auto-features process, added to return list
        """
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        git_root = session_context.git_root

        # Find the first (longest) level that fits
        include_features_tokens = sum(
            await count_feature_tokens(include_features, model)
        )
        max_auto_tokens = max_tokens - include_features_tokens
        all_features = include_features.copy()
        levels = [CodeMessageLevel.FILE_NAME]
        if not config.no_code_map:
            levels = [CodeMessageLevel.CMAP_FULL, CodeMessageLevel.CMAP] + levels
        for level in levels:
            level_features = _get_all_features(
                git_root,
                self.include_files,
                self.ignore_files,
                self.diff_context,
                self.code_map,
                level,
            )
            level_features = [
                f for f in level_features if f.path not in self.include_files
            ]
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
                i_cmap, cmap_feature = next(
                    (i, f) for i, f in enumerate(all_features) if f.path == abs_path
                )
                recovered_tokens = cmap_feature.count_tokens(model)
                new_tokens = code_feature.count_tokens(model)
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
        return list(paths.keys()), invalid_paths

    def exclude_file(self, path: Path):
        # TODO: Using get_include_files here isn't ideal; if the user puts in a glob that
        # matches files but doesn't match any files in context, we won't know what that glob is
        # and can't return it as an invalid path
        paths, invalid_paths = get_include_files([path], [])
        removed_paths = list[Path]()
        for new_path in paths.keys():
            if new_path in self.include_files:
                removed_paths.append(new_path)
                del self.include_files[new_path]
        return removed_paths, invalid_paths

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        level: CodeMessageLevel = CodeMessageLevel.INTERVAL,
    ) -> list[tuple[CodeFeature, float]]:
        """Return the top n features that are most similar to the query."""
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        git_root = session_context.git_root
        stream = session_context.stream

        if not config.use_embeddings:
            stream.send(
                "Embeddings are disabled. Enable with `/config use_embeddings true`",
                color="light_red",
            )
            return []

        all_features = _get_all_features(
            git_root,
            self.include_files,
            self.ignore_files,
            self.diff_context,
            self.code_map,
            level,
        )
        sim_scores = await get_feature_similarity_scores(query, all_features)
        all_features_scored = zip(all_features, sim_scores)
        all_features_sorted = sorted(
            all_features_scored, key=lambda x: x[1], reverse=True
        )
        if max_results is None:
            return all_features_sorted
        else:
            return all_features_sorted[:max_results]
