import fnmatch
import glob
import os
import re
from enum import Enum
from pathlib import Path
from typing import List, Set

from mentat.code_feature import CodeFeature
from mentat.errors import PathValidationError
from mentat.git_handler import get_git_root_for_path, get_non_gitignored_files
from mentat.interval import parse_intervals, split_intervals_from_path
from mentat.utils import is_file_text_encoded


class PathType(Enum):
    FILE = "file"
    FILE_INTERVAL = "file_interval"
    DIRECTORY = "directory"
    GLOB = "glob"


def is_interval_path(path: Path) -> bool:
    path, interval_str = split_intervals_from_path(path)
    if not interval_str:
        return False
    intervals = parse_intervals(interval_str)
    if len(intervals) == 0:
        return False
    return True


def get_path_type(path: Path) -> PathType:
    """Get the type of path.

    Args:
        `path` - An absolute path

    Return:
        A PathType enum
    """
    if not path.is_absolute():
        raise PathValidationError(f"Path {path} is not absolute")

    if path.is_file():
        return PathType.FILE
    elif is_interval_path(path):
        return PathType.FILE_INTERVAL
    elif path.is_dir():
        return PathType.DIRECTORY
    elif re.search(r"[\*\?\[\]]", str(path)):
        return PathType.GLOB
    else:
        raise PathValidationError(f"Path {path} does not exist")


def validate_file_path(path: Path, check_for_text: bool = True) -> None:
    if not path.is_absolute():
        raise PathValidationError(f"File {path} is not absolute")
    if not path.exists():
        raise PathValidationError(f"File {path} does not exist")
    if check_for_text and not is_file_text_encoded(path):
        raise PathValidationError(f"Unable to read file {path}")


def validate_file_interval_path(path: Path, check_for_text: bool = True) -> None:
    interval_path, interval_str = split_intervals_from_path(path)
    if not interval_path.is_absolute():
        raise PathValidationError(f"File interval {path} is not absolute")
    if not interval_path.exists():
        raise PathValidationError(f"File {interval_path} does not exist")
    if check_for_text and not is_file_text_encoded(interval_path):
        raise PathValidationError(f"Unable to read file {interval_path}")

    # check that there is at least one interval
    intervals = parse_intervals(interval_str)
    if len(intervals) == 0:
        raise PathValidationError(f"Unable to parse intervals for path {interval_path}")

    # check that each interval exists
    if check_for_text:
        with open(interval_path, "r") as f:
            line_count = len(f.read().split("\n"))
        for interval in intervals:
            if interval.start < 0 or interval.end > line_count + 1:
                raise PathValidationError(
                    f"Interval {interval.start}-{interval.end} is out of bounds for" f" file {interval_path}"
                )


def validate_glob_path(path: Path) -> None:
    if not path.is_absolute():
        raise PathValidationError(f"Glob path {path} is not absolute")
    try:
        glob.iglob(str(path)).__next__()
    except StopIteration:
        raise PathValidationError(f"Unable to validate glob path {path}")


def validate_and_format_path(path: Path | str, cwd: Path, check_for_text: bool = True) -> Path:
    """Validate and format a path.

    Args:
        `path` - A file path, file interval path, directory path, or a glob pattern
        `check_for_text` - Check if the file can be opened. Default to True

    Return:
        An absolute path
    """
    path = Path(path)

    # Resolve ~
    try:
        path = path.expanduser()
    except RuntimeError as e:
        raise PathValidationError(f"Error expanding path {path}: {e}")

    # Get absolute path
    if path.is_absolute():
        abs_path = path
    else:
        abs_path = cwd / path

    # Resolve path (remove any '..' or symlinks)
    abs_path = abs_path.resolve()

    # Validate path
    match get_path_type(abs_path):
        case PathType.FILE:
            validate_file_path(abs_path, check_for_text)
        case PathType.FILE_INTERVAL:
            validate_file_interval_path(abs_path, check_for_text)
        case PathType.DIRECTORY:
            pass
        case PathType.GLOB:
            validate_glob_path(abs_path)

    return abs_path


def match_path_with_patterns(path: Path, patterns: Set[Path]) -> bool:
    """Check if the given absolute path matches any of the patterns.

    Args:
        `path` - An absolute path
        `patterns` - A set of absolute paths/glob patterns

    Return:
        A boolean flag indicating if the path matches any of the patterns
    """
    if not path.is_absolute():
        raise PathValidationError(f"Path {path} is not absolute")
    for pattern in patterns:
        if not pattern.is_absolute():
            raise PathValidationError(f"Pattern {pattern} is not absolute")
        # Check if the path is relative to the pattern
        if path.is_relative_to(pattern):
            return True
        # Check if the pattern is a glob pattern match
        if fnmatch.fnmatch(str(path), str(pattern)):
            return True
    return False


def get_paths_for_directory(
    path: Path,
    include_patterns: Set[Path] = set(),
    exclude_patterns: Set[Path] = set(),
    recursive: bool = True,
) -> Set[Path]:
    """Get all file paths in a directory.

    Args:
        `path` - An absolute path to a directory on the filesystem
        `include_patterns` - An iterable of absolute paths/glob patterns to include
        `exclude_patterns` - An iterable of absolute paths/glob patterns to exclude
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

    for root, dirs, files in os.walk(path, topdown=True):
        root = Path(root)

        if get_git_root_for_path(root, raise_error=False):
            dirs[:] = list[str]()
            git_non_gitignored_paths = get_non_gitignored_files(root)
            for git_path in git_non_gitignored_paths:
                abs_git_path = root / git_path
                if not recursive and git_path.parent != Path("."):
                    continue
                if any(include_patterns) and not match_path_with_patterns(abs_git_path, include_patterns):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(abs_git_path, exclude_patterns):
                    continue
                paths.add(abs_git_path)

        else:
            filtered_dirs: List[str] = []
            for dir_ in dirs:
                abs_dir_path = root.joinpath(dir_)
                if any(include_patterns) and not match_path_with_patterns(abs_dir_path, include_patterns):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(abs_dir_path, exclude_patterns):
                    continue
                filtered_dirs.append(dir_)
            dirs[:] = filtered_dirs

            for file in files:
                abs_file_path = root.joinpath(file)
                if any(include_patterns) and not match_path_with_patterns(abs_file_path, include_patterns):
                    continue
                if any(exclude_patterns) and match_path_with_patterns(abs_file_path, exclude_patterns):
                    continue
                paths.add(abs_file_path)

            if not recursive:
                break
    paths = set(p.resolve() for p in paths if is_file_text_encoded(p))

    return paths


def get_code_features_for_path(
    path: Path,
    cwd: Path,
    include_patterns: Set[Path] = set(),
    exclude_patterns: Set[Path] = set(),
) -> Set[CodeFeature]:
    validated_path = validate_and_format_path(path, cwd)

    match get_path_type(validated_path):
        case PathType.FILE:
            code_features = set([CodeFeature(validated_path)])
        case PathType.FILE_INTERVAL:
            interval_path, interval_str = split_intervals_from_path(validated_path)
            intervals = parse_intervals(interval_str)
            code_features: Set[CodeFeature] = set()
            for interval in intervals:
                code_feature = CodeFeature(interval_path, interval)
                code_features.add(code_feature)
        case PathType.DIRECTORY:
            paths = get_paths_for_directory(validated_path, include_patterns, exclude_patterns)
            code_features = set(CodeFeature(p) for p in paths)
        case PathType.GLOB:
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
                include_patterns=(set([*include_patterns, validated_path]) if pattern != "*" else include_patterns),
                exclude_patterns=exclude_patterns,
                recursive=True,
            )
            code_features = set(CodeFeature(p) for p in paths)

    return code_features
