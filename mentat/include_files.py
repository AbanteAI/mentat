import fnmatch
import glob
import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Set

from mentat.code_feature import CodeFeature
from mentat.errors import PathValidationError
from mentat.git_handler import get_git_root_for_path, get_non_gitignored_files
from mentat.interval import parse_intervals
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


def validate_and_format_path(
    path: Path | str, cwd: Path, check_for_text: bool = True
) -> Path:
    """Validate and format a path.

    Args:
        `path` - A file path, file interval path, directory path, or a glob pattern
        `check_for_text` - Check if the file can be opened. Default to True

    Return:
        An absolute path
    """
    path = Path(path)

    # Get absolute path
    if path.is_absolute():
        abs_path = path
    else:
        abs_path = cwd.joinpath(path)

    # Resolve path (remove any '..')
    abs_path = abs_path.resolve()

    # Validate different path types
    # File
    if abs_path.is_file():
        if not abs_path.exists():
            raise PathValidationError(f"File {abs_path} does not exist")
        if check_for_text and not is_file_text_encoded(abs_path):
            raise PathValidationError(f"Unable to read file {abs_path}")
    # File interval
    elif len(str(abs_path).rsplit(":", 1)) > 1:
        _interval_path, interval_str = str(abs_path).rsplit(":", 1)
        interval_path = Path(_interval_path)
        if not interval_path.exists():
            raise PathValidationError(f"File {interval_path} does not exist")
        if check_for_text and not is_file_text_encoded(interval_path):
            raise PathValidationError(f"Unable to read file {interval_path}")
        intervals = parse_intervals(interval_str)
        if len(intervals) == 0:
            raise PathValidationError(
                f"Unable to parse intervals for path {interval_path}"
            )
    # Directory
    elif abs_path.is_dir():
        pass
    # Glob pattern
    elif re.search(r"[\*\?\[\]]", str(path)):
        try:
            glob.iglob(str(abs_path)).__next__()
        except StopIteration:
            raise PathValidationError(f"Unable to validate glob path {path}")
    else:
        raise PathValidationError(f"Unable to validate path {path}")

    return abs_path


def match_path_with_patterns(path: Path, patterns: Set[str]) -> bool:
    """Check if the given absolute path matches any of the patterns.

    TODO: enforce valid glob patterns? Right now we allow glob-like
    patterns (the one's that .gitignore uses). This feels weird imo.
    """
    if not path.is_absolute():
        raise PathValidationError(f"Path {path} is not absolute")

    for pattern in patterns:
        # Prepend '**' to relative patterns that are missing it
        if not Path(pattern).is_absolute() and not pattern.startswith("**"):
            if fnmatch.fnmatch(str(path), str(Path("**").joinpath(pattern))):
                return True
        if fnmatch.fnmatch(str(path), pattern):
            return True
        for part in path.parts:
            if fnmatch.fnmatch(str(part), pattern):
                return True

    return False


def get_paths_for_directory(
    path: Path,
    include_patterns: Iterable[Path | str] = [],
    exclude_patterns: Iterable[Path | str] = [],
    recursive: bool = True,
) -> Set[Path]:
    """Get all file paths in a directory.

    Args:
        `path` - An absolute path to a directory on the filesystem
        `include_patterns` - An iterable of paths and/or glob patterns to include
        `exclude_patterns` - An iterable of paths and/or glob patterns to exclude
        `recursive` - A boolean flag to recursive traverse child directories

    Return:
        A set of absolute file paths
    """
    paths: Set[Path] = set()

    if not path.exists():
        raise PathValidationError(f"Path {path} does not exist")
    if not path.is_dir():
        raise PathValidationError(f"Path {path} is not a directory")
    if not path.is_absolute():
        raise PathValidationError(f"Path {path} is not absolute")

    all_include_patterns = set(str(p) for p in include_patterns)
    all_exclude_patterns = set(str(p) for p in exclude_patterns)

    for root, dirs, files in os.walk(path, topdown=True):
        root = Path(root)

        if get_git_root_for_path(root, raise_error=False):
            dirs[:] = []
            git_non_gitignored_paths = get_non_gitignored_files(root)
            for git_path in git_non_gitignored_paths:
                abs_git_path = root.joinpath(git_path)
                if not recursive and git_path.parent != Path("."):
                    continue
                if any(include_patterns) and not match_path_with_patterns(
                    abs_git_path, all_include_patterns
                ):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(
                    abs_git_path, all_exclude_patterns
                ):
                    continue
                paths.add(abs_git_path)

        else:
            filtered_dirs: List[str] = []
            for dir_ in dirs:
                abs_dir_path = root.joinpath(dir_)
                if any(include_patterns) and not match_path_with_patterns(
                    abs_dir_path, all_include_patterns
                ):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(
                    abs_dir_path, all_exclude_patterns
                ):
                    continue
                filtered_dirs.append(dir_)
            dirs[:] = filtered_dirs

            for file in files:
                abs_file_path = root.joinpath(file)
                if any(include_patterns) and not match_path_with_patterns(
                    abs_file_path, all_include_patterns
                ):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(
                    abs_file_path, all_exclude_patterns
                ):
                    continue
                paths.add(abs_file_path)

            if not recursive:
                break

    return paths


def get_code_features_for_path(
    path: Path,
    cwd: Path,
    include_patterns: Iterable[Path | str] = [],
    exclude_patterns: Iterable[Path | str] = [],
) -> Set[CodeFeature]:
    validated_path = validate_and_format_path(path, cwd)

    # Directory
    if validated_path.is_dir():
        paths = get_paths_for_directory(
            validated_path, include_patterns, exclude_patterns
        )
        code_features = set(CodeFeature(p) for p in paths)
    # File
    elif validated_path.is_file():
        code_features = set([CodeFeature(validated_path)])
    # File interval
    elif len(str(validated_path).rsplit(":", 1)) > 1:
        interval_path, interval_str = str(validated_path).rsplit(":", 1)
        intervals = parse_intervals(interval_str)
        code_features: Set[CodeFeature] = set()
        for interval in intervals:
            code_feature = CodeFeature(
                f"{interval_path}:{interval.start}-{interval.end}"
            )
            code_features.add(code_feature)
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
            raise PathValidationError(f"Unable to parse glob pattern {validated_path}")
        root = Path().joinpath(*root_parts)
        paths = get_paths_for_directory(
            root,
            include_patterns=(
                [*include_patterns, pattern] if pattern != "*" else include_patterns
            ),
            exclude_patterns=exclude_patterns,
            recursive=True,
        )
        code_features = set(CodeFeature(p) for p in paths)

    return code_features


def build_path_tree(files: list[Path], cwd: Path):
    """Builds a tree of paths from a list of CodeFiles."""
    tree = dict[str, Any]()
    for file in files:
        path = os.path.relpath(file, cwd)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


def print_path_tree(
    tree: dict[str, Any], changed_files: set[Path], cur_path: Path, prefix: str = ""
):
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
