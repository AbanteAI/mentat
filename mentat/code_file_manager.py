import glob
import logging
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from termcolor import cprint

from .change_conflict_resolution import (
    resolve_insertion_conflicts,
    resolve_non_insertion_conflicts,
)
from .code_change import CodeChange, CodeChangeAction
from .config_manager import ConfigManager
from .git_handler import (
    get_git_diff_for_path,
    get_non_gitignored_files,
    get_paths_with_git_diffs,
)
from .user_input_manager import UserInputManager


def _build_path_tree(file_paths, git_root):
    tree = {}
    for path in file_paths:
        path = os.path.relpath(path, git_root)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


def _print_path_tree(tree, changed_files, cur_path, prefix=""):
    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            print(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            print(f"{prefix}└── ", end="")

        cur = os.path.join(cur_path, key)
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


def _is_file_text_encoded(file_path):
    try:
        # The ultimate filetype test
        with open(file_path) as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def _abs_file_paths_from_list(paths: Iterable[str], check_for_text: bool = True):
    file_paths_direct = set()
    file_paths_from_dirs = set()
    for path in paths:
        path = Path(path)
        if path.is_file():
            if check_for_text and not _is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                cprint(
                    f"Filepath {path} is not text encoded.",
                    "light_yellow",
                )
                raise KeyboardInterrupt
            file_paths_direct.add(os.path.realpath(path))
        elif path.is_dir():
            nonignored_files = set(
                map(
                    lambda f: os.path.realpath(os.path.join(path, f)),
                    get_non_gitignored_files(path),
                )
            )

            file_paths_from_dirs.update(
                filter(
                    lambda f: (not check_for_text) or _is_file_text_encoded(f),
                    nonignored_files,
                )
            )
    return file_paths_direct, file_paths_from_dirs


class CodeFileManager:
    def __init__(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str],
        user_input_manager: UserInputManager,
        config: ConfigManager,
        git_root: str,
    ):
        self.config = config
        self.git_root = git_root
        self._set_file_paths(paths, exclude_paths)
        self.user_input_manager = user_input_manager

        if self.file_paths:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(os.path.split(self.git_root)[1], "blue")
        _print_path_tree(
            _build_path_tree(self.file_paths, self.git_root),
            get_paths_with_git_diffs(self.git_root),
            self.git_root,
        )

    def _set_file_paths(
        self, paths: Iterable[str], exclude_paths: Iterable[str]
    ) -> None:
        invalid_paths = []
        for path in paths:
            if not os.path.exists(path):
                invalid_paths.append(path)
        if invalid_paths:
            cprint("Error:", "red", end=" ")
            cprint("The following paths do not exist:")
            print("\n".join(invalid_paths))
            print("Exiting...")
            exit()

        excluded_files, excluded_files_from_dir = _abs_file_paths_from_list(
            exclude_paths, check_for_text=False
        )

        glob_excluded_files = set(
            os.path.join(self.git_root, file)
            for glob_path in self.config.file_exclude_glob_list()
            # If the user puts a / at the beginning, it will try to look in root directory
            for file in glob.glob(
                pathname=glob_path,
                root_dir=self.git_root,
                recursive=True,
            )
        )
        file_paths_direct, file_paths_from_dirs = _abs_file_paths_from_list(
            paths, check_for_text=True
        )

        # config glob excluded files only apply to files added from directories
        file_paths_from_dirs -= glob_excluded_files

        self.file_paths = list(
            (file_paths_direct | file_paths_from_dirs)
            - (excluded_files | excluded_files_from_dir)
        )

    def _read_file(self, abs_path) -> Iterable[str]:
        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        return lines

    def _read_all_file_lines(self) -> None:
        self.file_lines = dict()
        for abs_path in self.file_paths:
            self.file_lines[abs_path] = self._read_file(abs_path)

    def get_code_message(self):
        self._read_all_file_lines()
        code_message = ["Code Files:\n"]
        for abs_path in self.file_paths:
            rel_path = os.path.relpath(abs_path, self.git_root)

            # We always want to give GPT posix paths
            posix_rel_path = Path(rel_path).as_posix()
            code_message.append(posix_rel_path)

            for i, line in enumerate(self.file_lines[abs_path], start=1):
                code_message.append(f"{i}:{line}")
            code_message.append("")

            git_diff_output = get_git_diff_for_path(self.git_root, rel_path)
            if git_diff_output:
                code_message.append("Current git diff for this file:")
                code_message.append(f"{git_diff_output}")

        return "\n".join(code_message)

    def _handle_delete(self, delete_change):
        file_path = os.path.join(self.git_root, delete_change.file)
        if not os.path.exists(file_path):
            logging.error(f"Path {file_path} non-existent on delete")
            return

        cprint(f"Are you sure you want to delete {delete_change.file}?", "red")
        if self.user_input_manager.ask_yes_no(default_yes=False):
            logging.info(f"Deleting file {file_path}")
            cprint(f"Deleting {delete_change.file}...")
            self.file_paths.remove(file_path)
            os.remove(file_path)
        else:
            cprint(f"Not deleting {delete_change.file}")

    def _get_new_code_lines(self, changes) -> Iterable[str]:
        if len(set(map(lambda change: change.file, changes))) > 1:
            raise Exception("All changes passed in must be for the same file")

        changes = sorted(changes, reverse=True)

        # We resolve insertion conflicts twice because non-insertion conflicts
        # might move insert blocks outside of replace/delete blocks and cause
        # them to conflict again
        changes = resolve_insertion_conflicts(changes, self.user_input_manager, self)
        changes = resolve_non_insertion_conflicts(changes, self.user_input_manager)
        changes = resolve_insertion_conflicts(changes, self.user_input_manager, self)
        if not changes:
            return []

        rel_path = changes[0].file
        abs_path = os.path.join(self.git_root, rel_path)
        new_code_lines = self.file_lines[abs_path].copy()
        if new_code_lines != self._read_file(abs_path):
            logging.info(f"File '{rel_path}' changed while generating changes")
            cprint(
                f"File '{rel_path}' changed while generating; current file changes"
                " will be erased. Continue?",
                color="light_yellow",
            )
            if not self.user_input_manager.ask_yes_no(default_yes=False):
                cprint(f"Not applying changes to file {rel_path}.")
                return None

        # Necessary in case the model needs to insert past the end of the file
        last_line = len(new_code_lines) + 1
        largest_changed_line = math.ceil(changes[0].last_changed_line)
        if largest_changed_line > last_line:
            new_code_lines += [""] * (largest_changed_line - last_line)

        min_changed_line = largest_changed_line + 1
        for i, change in enumerate(changes):
            if change.last_changed_line >= min_changed_line:
                raise ValueError(f"Change line number overlap in file {change.file}")
            min_changed_line = change.first_changed_line
            new_code_lines = change.apply(new_code_lines)
        return new_code_lines

    def write_changes_to_files(self, code_changes: list[CodeChange]) -> None:
        files_to_write = dict()
        file_changes = defaultdict(list)
        for code_change in code_changes:
            rel_path = code_change.file
            if code_change.action == CodeChangeAction.CreateFile:
                cprint(f"Creating new file {rel_path}", color="light_green")
                files_to_write[rel_path] = code_change.code_lines
            elif code_change.action == CodeChangeAction.DeleteFile:
                self._handle_delete(code_change)
            else:
                file_changes[rel_path].append(code_change)

        for file_path, changes in file_changes.items():
            new_code_lines = self._get_new_code_lines(changes)
            if new_code_lines:
                files_to_write[file_path] = new_code_lines

        for rel_path, code_lines in files_to_write.items():
            file_path = os.path.join(self.git_root, rel_path)
            if file_path not in self.file_paths:
                # newly created files added to Mentat's context
                logging.info(f"Adding new file {file_path} to context")
                self.file_paths.append(file_path)
                # create any missing directories in the path
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write("\n".join(code_lines))
