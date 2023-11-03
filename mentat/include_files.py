import fnmatch
from ipdb import set_trace
import re
import os
from pathlib import Path
from typing import Any, Iterable, Set, List

from mentat.code_feature import CodeFeature
from mentat.git_handler import check_is_git_repo, get_non_gitignored_files
from mentat.session_context import SESSION_CONTEXT


# TODO: replace this with something that doesn't load the file into memory
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


def validate_and_format_path(path: Path, cwd: Path, check_for_text: bool = True) -> Path:
    """Validate and format a path.
    `path` can be a file path, file interval path, directory path, or a glob pattern.
    """
    # set_trace()
    # Get absolute path
    if path.is_absolute():
        abs_path = path
    else:
        abs_path = cwd.joinpath(path)

    # Validate different path types
    # File
    if abs_path.is_file():
        if not abs_path.exists():
            raise PathValidationException(f"File {abs_path} does not exist")
        if check_for_text and not is_file_text_encoded(abs_path):
            raise PathValidationException(f"Unable to read file {abs_path}")
    # File interval
    elif ":" in str(abs_path):
        interval_path, interval_str = str(abs_path).split(":", 1)
        abs_interval_path = Path(interval_path)
        if not Path(abs_interval_path).exists():
            raise PathValidationException(f"File interval {abs_path} does not exist")
        if check_for_text and not is_file_text_encoded(abs_interval_path):
            raise PathValidationException(f"Unable to read file interval {abs_path}")
        abs_path = abs_interval_path.joinpath(interval_str)
    # Directory
    elif abs_path.is_dir():
        if not abs_path.exists():
            raise PathValidationException(f"Directory {abs_path} does not exist")
    # Glob pattern
    elif re.search(r"[\*\?\[\]]", str(path)):
        pass
    else:
        raise PathValidationException(f"Unable to validate path {path}")

    return abs_path


def match_path_with_patterns(path: Path, patterns: Set[str]) -> bool:
    """Check if the given absolute path matches any of the patterns."""

    if not path.is_absolute():
        raise PathValidationException(f"Path {path} is not absolute")

    # if "glob_test" in str(path):
    #     set_trace()

    # if glob.globmatch(path, "|".join(patterns)):
    #     return True
    for pattern in patterns:
        # Prepend '**' to relative patterns that are missing it
        if not Path(pattern).is_absolute() and not pattern.startswith("**"):
            pattern = str(Path("**").joinpath(pattern))

        # # pattern match full path
        # if pattern in str(path):
        #     return True
        # wildcard match full path
        if fnmatch.fnmatch(str(path), pattern):
            return True
        # # wildcard match path parts
        # for part in path.parts:
        #     if fnmatch.fnmatch(part, pattern):
        #         return True
    return False


def get_paths_for_directory(
    path: Path,
    include_patterns: Iterable[Path | str] = [],
    ignore_patterns: Iterable[Path | str] = [],
    recursive: bool = False,
) -> Set[Path]:
    """Get all file paths in a directory.

    Args:
        `path` - An absolute path to a directory on the filesystem
        `include_patterns` - An iterable of paths and/or glob patterns to include
        `ignore_patterns` - An iterable of paths and/or glob patterns to exclude
        `recursive` - A boolean flag to recursive traverse child directories

    Return:
        A set of absolute file paths
    """
    paths: Set[Path] = set()

    if not path.exists():
        raise PathValidationException(f"Path {path} does not exist")
    if not path.is_dir():
        raise PathValidationException(f"Path {path} is not a directory")
    if not path.is_absolute():
        raise PathValidationException(f"Path {path} is not absolute")

    all_include_patterns = set(str(p) for p in include_patterns)
    all_ignore_patterns = set(str(p) for p in ignore_patterns)

    for root, dirs, files in os.walk(path, topdown=True):
        root = Path(root)

        if check_is_git_repo(root):
            dirs[:] = []
            git_non_gitignored_paths = get_non_gitignored_files(root)
            for git_path in git_non_gitignored_paths:
                abs_git_path = root.joinpath(git_path)
                if not recursive and git_path.parent != Path("."):
                    continue
                if any(include_patterns) and not match_path_with_patterns(abs_git_path, all_include_patterns):
                    continue
                if any(ignore_patterns) and match_path_with_patterns(abs_git_path, all_ignore_patterns):
                    continue
                paths.add(abs_git_path)

        else:
            filtered_dirs: List[str] = []
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
