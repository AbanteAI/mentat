import glob
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from mentat.code_feature import CodeFeature, parse_intervals
from mentat.git_handler import get_non_gitignored_files
from mentat.session_context import SESSION_CONTEXT


def expand_paths(paths: list[Path]) -> tuple[list[Path], list[str]]:
    """Expand paths/globs into a list of absolute paths."""
    globbed_paths = set[str]()
    invalid_paths = set[str]()
    for path in paths:
        new_paths = glob.glob(pathname=str(path), recursive=True)
        if new_paths:
            globbed_paths.update(new_paths)
        elif Path(path).exists():
            globbed_paths.add(str(path))
        else:
            split = str(path).rsplit(":", 1)
            p = Path(split[0])
            if len(split) > 1:
                intervals = parse_intervals(split[1])
            else:
                intervals = None
            if Path(p).exists() and intervals:
                for interval in intervals:
                    globbed_paths.add(f"{p}:{interval.start}-{interval.end}")
            else:
                invalid_paths.add(str(path))
    return [Path(path).resolve() for path in globbed_paths], list(invalid_paths)


def is_file_text_encoded(abs_path: Path):
    """Checks if a file is text encoded."""
    try:
        # The ultimate filetype test
        with open(abs_path, "r") as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def abs_files_from_list(paths: list[Path], check_for_text: bool = True):
    """Returns a set of CodeFiles from a list of paths."""
    files_direct = set[CodeFeature]()
    file_paths_from_dirs = set[Path]()
    invalid_paths = list[str]()
    for path in paths:
        file = CodeFeature(os.path.realpath(path))
        path = Path(file.path)
        if path.is_file():
            if check_for_text and not is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                invalid_paths.append(str(path))
            else:
                files_direct.add(file)
        elif path.is_dir():
            nonignored_files = set(
                map(
                    lambda f: Path(os.path.realpath(path / f)),
                    get_non_gitignored_files(path),
                )
            )

            file_paths_from_dirs.update(
                filter(
                    lambda f: (not check_for_text) or is_file_text_encoded(f),
                    nonignored_files,
                )
            )

    files_from_dirs = set(CodeFeature(path.resolve()) for path in file_paths_from_dirs)
    return files_direct, files_from_dirs, invalid_paths


def get_ignore_files(ignore_paths: list[Path]) -> set[Path]:
    """Returns a set of files to ignore from a list of ignore paths."""

    ignore_paths, _ = expand_paths(ignore_paths)

    files_direct, files_from_dirs, _ = abs_files_from_list(
        ignore_paths, check_for_text=False
    )
    return {f.path for f in files_direct | files_from_dirs}


def get_include_files(
    paths: list[Path], exclude_paths: list[Path]
) -> tuple[Dict[Path, list[CodeFeature]], list[str]]:
    """Returns a complete list of text files in a given set of include/exclude Paths."""
    session_context = SESSION_CONTEXT.get()
    git_root = session_context.git_root
    config = session_context.config

    paths, invalid_paths = expand_paths(paths)
    exclude_paths, _ = expand_paths(exclude_paths)

    excluded_files_direct, excluded_files_from_dirs, _ = abs_files_from_list(
        exclude_paths, check_for_text=False
    )
    excluded_files = set(
        map(lambda f: f.path, excluded_files_direct | excluded_files_from_dirs)
    )

    glob_excluded_files = set(
        Path(os.path.join(git_root, file))
        for glob_path in config.file_exclude_glob_list
        # If the user puts a / at the beginning, it will try to look in root directory
        for file in glob.glob(
            pathname=glob_path,
            root_dir=git_root,
            recursive=True,
        )
    )
    files_direct, files_from_dirs, non_text_paths = abs_files_from_list(
        paths, check_for_text=True
    )
    invalid_paths.extend(non_text_paths)

    # config glob excluded files only apply to files added from directories
    files_from_dirs = [
        file
        for file in files_from_dirs
        if file.path.resolve() not in glob_excluded_files
    ]
    files_direct.update(files_from_dirs)

    files: defaultdict[Path, list[CodeFeature]] = defaultdict(list)
    for file in files_direct:
        if file.path not in excluded_files:
            files[file.path.resolve()].append(file)

    return dict(files), invalid_paths


def build_path_tree(files: list[Path], git_root: Path):
    """Builds a tree of paths from a list of CodeFiles."""
    tree = dict[str, Any]()
    for file in files:
        path = os.path.relpath(file, git_root)
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


def print_invalid_path(invalid_path: str):
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    git_root = session_context.git_root

    abs_path = Path(invalid_path).absolute()
    if "*" in invalid_path:
        stream.send(
            f"The glob pattern {invalid_path} did not match any files",
            color="light_red",
        )
    elif not abs_path.exists():
        stream.send(
            f"The path {invalid_path} does not exist and was skipped", color="light_red"
        )
    elif not is_file_text_encoded(abs_path):
        rel_path = abs_path.relative_to(git_root)
        stream.send(
            f"The file {rel_path} is not text encoded and was skipped",
            color="light_red",
        )
    else:
        stream.send(f"The file {invalid_path} was skipped", color="light_red")
