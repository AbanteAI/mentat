import fnmatch
import os
import re
from pathlib import Path
from typing import Iterable, List, Set

from ipdb import set_trace

from mentat.errors import PathValidationException
from mentat.git_handler import check_is_git_repo, get_non_gitignored_files


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


def validate_and_format_path(path: Path, cwd: Path, check_for_text: bool = True) -> Path:
    """Validate and format a path.

    Args:
        `path` - A file path, file interval path, directory path, or a glob pattern
        `check_for_text` - Check if the file can be opened. Default to True

    Return:
        An absolute path
    """
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
        _interval_path, interval_str = str(abs_path).split(":", 1)
        interval_path = Path(_interval_path)
        if not interval_path.exists():
            raise PathValidationException(f"File interval {abs_path} does not exist")
        if check_for_text and not is_file_text_encoded(interval_path):
            raise PathValidationException(f"Unable to read file interval {abs_path}")
        abs_path = Path(f"{interval_path}:{interval_str}")
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
    """Check if the given absolute path matches any of the patterns.

    TODO: enforce valid glob patterns? Right now we allow glob-like
    patterns (the one's that .gitignore uses). This feels weird imo.
    """
    if not path.is_absolute():
        raise PathValidationException(f"Path {path} is not absolute")

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
                if any(include_patterns) and not match_path_with_patterns(abs_dir_path, all_include_patterns):
                    continue
                if any(ignore_patterns) and match_path_with_patterns(abs_dir_path, all_ignore_patterns):
                    continue
                filtered_dirs.append(dir_)
            dirs[:] = filtered_dirs

            for file in files:
                abs_file_path = root.joinpath(file)
                if any(include_patterns) and not match_path_with_patterns(abs_file_path, all_include_patterns):
                    continue
                if any(ignore_patterns) and match_path_with_patterns(abs_file_path, all_ignore_patterns):
                    continue
                paths.add(abs_file_path)

            if not recursive:
                break

    return paths
