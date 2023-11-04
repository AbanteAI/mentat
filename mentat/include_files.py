import re
import os
from pathlib import Path
from typing import Any, Iterable, Set, List

from mentat.code_feature import CodeFeature
from mentat.session_context import SESSION_CONTEXT
from mentat.errors import PathValidationException

from mentat.utils.path import validate_and_format_path, get_paths_for_directory


def get_code_features_for_path(
    path: Path,
    cwd: Path,
    include_patterns: Iterable[Path | str] = [],
    ignore_patterns: Iterable[Path | str] = [],
) -> Set[CodeFeature]:
    validated_path = validate_and_format_path(path, cwd)

    # Directory
    if validated_path.is_dir():
        paths = get_paths_for_directory(validated_path, include_patterns, ignore_patterns)
        code_features = set(CodeFeature(p) for p in paths)
    # File or File Interval
    elif validated_path.is_file() or ":" in str(validated_path):
        code_features = set([CodeFeature(validated_path)])
    # Glob pattern
    else:
        root_parts: List[str] = []
        pattern: str | None = None
        for i, part in enumerate(validated_path.parts):
            if re.search(r"[\*\?\[\]]", str(part)):
                pattern = str(Path().joinpath(*validated_path.parts[i:]))
                break
            root_parts.append(part)
        if pattern is None:
            raise PathValidationException(f"Unable to parse glob pattern {validated_path}")
        root = Path().joinpath(*root_parts)
        all_include_patterns = [*include_patterns]
        if pattern != "*":
            all_include_patterns.append(pattern)
        paths = get_paths_for_directory(
            root, include_patterns=all_include_patterns, ignore_patterns=ignore_patterns, recursive=True
        )
        code_features = set(CodeFeature(p) for p in paths)

    return code_features


def build_path_tree(code_features: List[CodeFeature], cwd: Path):
    """Builds a tree of paths from a list of CodeFeatures."""
    tree = dict[str, Any]()
    for code_feature in code_features:
        path = os.path.relpath(code_feature.path, cwd)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


def print_path_tree(tree: dict[str, Any], changed_files: set[Path], cur_path: Path, prefix: str = ""):
    """Prints a tree of paths, with changed files highlighted."""
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            stream.send(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            stream.send(f"{prefix}└── ", end="")

        cur = cur_path / key
        star = "* " if cur in changed_files else ""
        if tree[key]:
            color = "blue"
        elif star:
            color = "green"
        else:
            color = None
        stream.send(f"{star}{key}", color=color)
        if tree[key]:
            print_path_tree(tree[key], changed_files, cur, new_prefix)
