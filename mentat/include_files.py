import glob
import logging
import os
from pathlib import Path
from typing import Any, Dict

from mentat.code_file import CodeFile, parse_intervals
from mentat.config_manager import CONFIG_MANAGER
from mentat.git_handler import GIT_ROOT, get_non_gitignored_files
from mentat.session_stream import SESSION_STREAM


def expand_paths(paths: list[Path]) -> list[Path]:
    """Expand paths/globs into a list of absolute paths."""
    globbed_paths = set[str]()
    invalid_paths = set[str]()
    for path in paths:
        new_paths = glob.glob(pathname=str(path), recursive=True)
        if new_paths:
            globbed_paths.update(new_paths)
        else:
            split = str(path).rsplit(":", 1)
            p = Path(split[0])
            if len(split) > 1:
                intervals = parse_intervals(split[1])
            else:
                intervals = None
            if Path(p).exists() and intervals:
                globbed_paths.add(str(path))
            else:
                invalid_paths.add(str(path))
    return [Path(path).resolve() for path in globbed_paths]


def is_file_text_encoded(file_path: Path):
    """Checks if a file is text encoded."""
    try:
        # The ultimate filetype test
        with open(file_path, "r") as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def abs_files_from_list(paths: list[Path], check_for_text: bool = True):
    """Returns a set of CodeFiles from a list of paths."""
    files_direct = set[CodeFile]()
    file_paths_from_dirs = set[Path]()
    invalid_paths = list[str]()
    for path in paths:
        file = CodeFile(os.path.realpath(path))
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

    files_from_dirs = set(CodeFile(path.resolve()) for path in file_paths_from_dirs)
    return files_direct, files_from_dirs, invalid_paths


def get_include_files(
    paths: list[Path], exclude_paths: list[Path]
) -> tuple[Dict[Path, CodeFile], list[str]]:
    """Returns a complete list of text files in a given set of include/exclude Paths."""
    git_root = GIT_ROOT.get()
    config = CONFIG_MANAGER.get()

    paths = expand_paths(paths)
    exclude_paths = expand_paths(exclude_paths)

    excluded_files_direct, excluded_files_from_dirs, _ = abs_files_from_list(
        exclude_paths, check_for_text=False
    )
    excluded_files = set(
        map(lambda f: f.path, excluded_files_direct | excluded_files_from_dirs)
    )

    glob_excluded_files = set(
        Path(os.path.join(git_root, file))
        for glob_path in config.file_exclude_glob_list()
        # If the user puts a / at the beginning, it will try to look in root directory
        for file in glob.glob(
            pathname=glob_path,
            root_dir=git_root,
            recursive=True,
        )
    )
    files_direct, files_from_dirs, invalid_paths = abs_files_from_list(
        paths, check_for_text=True
    )

    # config glob excluded files only apply to files added from directories
    files_from_dirs = [
        file
        for file in files_from_dirs
        if file.path.resolve() not in glob_excluded_files
    ]
    files_direct.update(files_from_dirs)

    files = dict[Path, CodeFile]()
    for file in files_direct:
        if file.path not in excluded_files:
            files[file.path.resolve()] = file

    return files, invalid_paths


def build_path_tree(files: list[CodeFile], git_root: Path):
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


async def print_path_tree(
    tree: dict[str, Any], changed_files: set[Path], cur_path: Path, prefix: str = ""
):
    """Prints a tree of paths, with changed files highlighted."""
    stream = SESSION_STREAM.get()
    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            await stream.send(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            await stream.send(f"{prefix}└── ", end="")

        cur = cur_path / key
        star = "* " if cur in changed_files else ""
        if tree[key]:
            color = "blue"
        elif star:
            color = "green"
        else:
            color = None
        await stream.send(f"{star}{key}", color=color)
        if tree[key]:
            await print_path_tree(tree[key], changed_files, cur, new_prefix)
