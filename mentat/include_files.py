import fnmatch
from ipdb import set_trace
import re
import os
from pathlib import Path
from typing import Any, Iterable, Set, List

from mentat.code_feature import CodeFeature
from mentat.git_handler import check_is_git_repo, get_non_gitignored_files
from mentat.session_context import SESSION_CONTEXT


# TODO: don't load the file into memory
def is_file_text_encoded(abs_path: Path):
    """Checks if a file is text encoded."""
    try:
        # The ultimate filetype test
        with open(abs_path, "r") as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


class PathValidationException(Exception):
    pass


def match_path_with_patterns(path: Path, patterns: Set[str]) -> bool:
    """Check if the given path matches any of the patterns."""
    for pattern in patterns:
        # check entire path
        if fnmatch.fnmatch(str(path), pattern):
            return True
        # check file parts
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def get_paths_for_directory(
    path: Path,
    include_patterns: Iterable[Path | str] = [],
    ignore_patterns: Iterable[Path | str] = [],
    recursive: bool = False,
) -> Set[Path]:
    paths: Set[Path] = set()

    abs_path = path.resolve()
    if not abs_path.exists():
        raise PathValidationException(f"Path {path} does not exist")
    if not abs_path.is_dir():
        raise PathValidationException(f"Path {path} is not a directory")

    all_include_patterns = set(str(p) for p in include_patterns)
    all_ignore_patterns = set(str(p) for p in ignore_patterns)

    for root, dirs, files in os.walk(abs_path, topdown=True):
        root = Path(root)

        if check_is_git_repo(root):
            dirs[:] = []
            git_non_gitignored_paths = get_non_gitignored_files(root)
            for git_path in git_non_gitignored_paths:
                if not recursive and git_path.parent != Path("."):
                    continue
                if any(include_patterns) and not match_path_with_patterns(git_path, all_include_patterns):
                    continue
                if any(ignore_patterns) and match_path_with_patterns(git_path, all_ignore_patterns):
                    continue
                paths.add(root.joinpath(git_path))

        else:
            filtered_dirs: Iterable[str] = []
            for dir_ in dirs:
                abs_dir_path = root.joinpath(dir_)
                if not match_path_with_patterns(abs_dir_path, all_include_patterns):
                    continue
                if match_path_with_patterns(abs_dir_path, all_ignore_patterns):
                    continue
                filtered_dirs.append(dir_)
            dirs[:] = filtered_dirs

            for file in files:
                abs_file_path = root.joinpath(file)
                if not match_path_with_patterns(abs_file_path, all_include_patterns):
                    continue
                if match_path_with_patterns(abs_file_path, all_ignore_patterns):
                    continue
                paths.add(abs_file_path)

            if not recursive:
                break

    return paths


def validate_path(path: Path | str, check_for_text: bool = True) -> None:
    if ":" in str(path):
        interval_path, _ = str(path).split(":", 1)
        abs_path = Path(interval_path).resolve()
    else:
        abs_path = Path(path).resolve()

    if not abs_path.exists():
        raise PathValidationException(f"Path {abs_path} does not exist")
    if check_for_text and not is_file_text_encoded(abs_path):
        raise PathValidationException(f"Unable to read file {abs_path}")


def get_code_features_for_path(
    path: Path,
    include_patterns: Iterable[Path | str] = [],
    ignore_patterns: Iterable[Path | str] = [],
) -> Set[CodeFeature]:
    # Directory
    if path.is_dir():
        paths = get_paths_for_directory(path, include_patterns, ignore_patterns)
        code_features = set(CodeFeature(p) for p in paths)
    # File
    elif path.is_file():
        validate_path(path)
        code_features = set([CodeFeature(path)])
    # File Interval
    elif ":" in str(path):
        interval_path, _ = str(path).split(":", 1)
        validate_path(interval_path)
        code_features = set([CodeFeature(interval_path)])
    # Glob pattern
    else:
        root_parts: List[str] = []
        pattern: str | None = None
        for i, part in enumerate(path.parts):
            if re.search(r"[\*\?\[\]]", str(path)):
                pattern = str(Path().joinpath(*path.parts[i:]))
                break
            root_parts.append(part)
        if pattern is None:
            raise PathValidationException(f"Unable to parse glob pattern {path}")
        root = Path().joinpath(*root_parts)
        paths = get_paths_for_directory(
            root, include_patterns=[pattern, *include_patterns], ignore_patterns=ignore_patterns, recursive=True
        )
        code_features = set(CodeFeature(p) for p in paths)

    return code_features


def build_path_tree(files: list[CodeFeature], git_root: Path):
    """Builds a tree of paths from a list of CodeFiles."""
    tree = dict[str, Any]()
    for file in files:
        path = os.path.relpath(file.path, git_root)
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
