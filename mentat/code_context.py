from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent
from typing import Optional

import attr

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
    get_include_files,
    is_file_text_encoded,
    print_invalid_path,
    print_path_tree,
)
from mentat.llm_api import count_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream
from mentat.utils import sha256


@attr.define
class CodeContextSettings:
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False
    use_embeddings: bool = False
    auto_tokens: Optional[int] = None


def _get_all_features(
    git_root: Path,
    include_files: dict[Path, CodeFeature],
    diff_context: DiffContext,
    code_map: bool,
    level: Optional[CodeMessageLevel] = None,
) -> list[CodeFeature]:
    """Return a list of all features in the git root, optionally filtered by level."""

    _features = list[CodeFeature]()
    for path in get_non_gitignored_files(git_root):
        abs_path = git_root / path
        if (
            abs_path in include_files
            or abs_path.is_dir()
            or not is_file_text_encoded(abs_path)
        ):
            continue

        diff_target = diff_context.target if abs_path in diff_context.files else None
        user_included = path in include_files
        if level is None:
            # Return intervals if code_map is enabled, otherwise return the full file
            level = CodeMessageLevel.CODE
            _feature = CodeFeature(
                abs_path, level=level, diff=diff_target, user_included=user_included
            )
            if code_map:
                _split_features = split_file_into_intervals(git_root, _feature)
                _features += _split_features
            else:
                _features.append(_feature)
        else:
            _feature = CodeFeature(
                abs_path, level=level, diff=diff_target, user_included=user_included
            )
            _features.append(_feature)

    return _features


class CodeContext:
    settings: CodeContextSettings
    include_files: dict[Path, CodeFeature]
    diff_context: DiffContext
    code_map: bool = True
    features: list[CodeFeature] = []

    def __init__(
        self,
        stream: SessionStream,
        git_root: Path,
        settings: CodeContextSettings,
    ):
        self.settings = settings
        self.diff_context = DiffContext(
            stream, git_root, self.settings.diff, self.settings.pr_diff
        )
        # TODO: This is a dict so we can quickly reference either a path (key)
        # or the CodeFeature (value) and its interval. Redundant.
        self.include_files = {}

    def set_paths(self, paths: list[Path], exclude_paths: list[Path]):
        self.include_files, invalid_paths = get_include_files(paths, exclude_paths)
        for invalid_path in invalid_paths:
            print_invalid_path(invalid_path)

    def set_code_map(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

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
                stream.send(ctags_disabled_message, color="yellow")
                self.settings.no_code_map = True
                self.code_map = False
            else:
                self.code_map = True

    def display_context(self):
        """Display the baseline context: included files and auto-context settings"""
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
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
        auto = self.settings.auto_tokens
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
        _max_user = self.settings.auto_tokens
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
        session_context = SESSION_CONTEXT.get()
        git_root = session_context.git_root

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
            _features = _get_all_features(
                git_root, self.include_files, self.diff_context, self.code_map, level
            )
            level_length = sum(await count_feature_tokens(_features, model))
            if level_length < max_auto_tokens:
                all_features += _features
                break

        # Sort by relative path
        def _feature_relative_path(f: CodeFeature) -> str:
            return os.path.relpath(f.path, git_root)

        all_features = sorted(all_features, key=_feature_relative_path)

        # If there's room, convert cmap features to code features (full text)
        # starting with the highest-scoring.
        cmap_features_tokens = sum(await count_feature_tokens(all_features, model))
        max_sim_tokens = max_tokens - cmap_features_tokens
        if self.settings.auto_tokens is not None:
            max_sim_tokens = min(max_sim_tokens, self.settings.auto_tokens)

        if self.settings.use_embeddings and max_sim_tokens > 0 and prompt != "":
            sim_tokens = 0

            # Get embedding-similarity scores for all files
            all_code_features_sorted = await self.search(query=prompt)
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
        self, query: str, max_results: int | None = None
    ) -> list[tuple[CodeFeature, float]]:
        """Return the top n features that are most similar to the query."""
        session_context = SESSION_CONTEXT.get()
        git_root = session_context.git_root
        stream = session_context.stream

        if not self.settings.use_embeddings:
            stream.send(
                "Embeddings are disabled. To enable, restart with '--use-embeddings'.",
                color="light_red",
            )
            return []

        all_features = _get_all_features(
            git_root, self.include_files, self.diff_context, self.code_map
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
