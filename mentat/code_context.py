import glob
import logging
import os
from pathlib import Path
from typing import Any, Dict

from termcolor import cprint

from .code_file import CodeFile
from .config_manager import ConfigManager
from .errors import UserError
from .git_handler import get_non_gitignored_files, get_paths_with_git_diffs


def _is_file_text_encoded(file_path: Path):
    try:
        # The ultimate filetype test
        with open(file_path) as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def _abs_files_from_list(paths: list[Path], check_for_text: bool = True):
    files_direct = set[CodeFile]()
    file_paths_from_dirs = set[Path]()
    for path in paths:
        file = CodeFile(path)
        path = Path(file.path)
        if path.is_file():
            if check_for_text and not _is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                raise UserError(f"File path {path} is not text encoded.")
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
                    lambda f: (not check_for_text) or _is_file_text_encoded(f),
                    nonignored_files,
                )
            )

    files_from_dirs = [CodeFile(path) for path in file_paths_from_dirs]
    return files_direct, files_from_dirs


def _get_files(
    config: ConfigManager, paths: list[Path], exclude_paths: list[Path]
) -> Dict[Path, CodeFile]:
    excluded_files_direct, excluded_files_from_dirs = _abs_files_from_list(
        exclude_paths, check_for_text=False
    )
    excluded_files, excluded_files_from_dir = set(
        map(lambda f: f.path, excluded_files_direct)
    ), set(map(lambda f: f.path, excluded_files_from_dirs))

    glob_excluded_files = set(
        os.path.join(config.git_root, file)
        for glob_path in config.file_exclude_glob_list()
        # If the user puts a / at the beginning, it will try to look in root directory
        for file in glob.glob(
            pathname=glob_path,
            root_dir=config.git_root,
            recursive=True,
        )
    )
    files_direct, files_from_dirs = _abs_files_from_list(paths, check_for_text=True)

    # config glob excluded files only apply to files added from directories
    files_from_dirs = [
        file
        for file in files_from_dirs
        if str(file.path.resolve()) not in glob_excluded_files
    ]

    files_direct.update(files_from_dirs)

    files = dict[Path, CodeFile]()
    for file in files_direct:
        if file.path not in excluded_files | excluded_files_from_dir:
            files[Path(os.path.realpath(file.path))] = file

    return files


def _build_path_tree(files: list[CodeFile], git_root: Path):
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


def _print_path_tree(
    tree: dict[str, Any], changed_files: set[Path], cur_path: Path, prefix: str = ""
):
    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            print(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            print(f"{prefix}└── ", end="")

        cur = cur_path / key
        star = "* " if cur in changed_files else ""
        if tree[key]:
            color = "blue"
        elif star:
            color = "green"
        else:
            color = None
        cprint(f"{star}{key}", color)
        if tree[key]:
            _print_path_tree(tree[key], changed_files, cur, new_prefix)


class CodeContext:
    def __init__(
        self,
        config: ConfigManager,
        paths: list[Path],
        exclude_paths: list[Path],
    ):
        self.config = config
        self.files = _get_files(self.config, paths, exclude_paths)

    def display_context(self):
        if self.files:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(self.config.git_root.name, "blue")
        _print_path_tree(
            _build_path_tree(list(self.files.values()), self.config.git_root),
            get_paths_with_git_diffs(self.config.git_root),
            self.config.git_root,
        )
        print()
