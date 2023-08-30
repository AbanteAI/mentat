import logging
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Union

from termcolor import cprint

from .change_conflict_resolution import (
    resolve_insertion_conflicts,
    resolve_non_insertion_conflicts,
)
from .code_change import CodeChange, CodeChangeAction
from .code_context import CodeContext
from .code_file import CodeFile
from .config_manager import ConfigManager
from .errors import MentatError
from .git_handler import get_git_diff_for_path, get_paths_with_git_diffs
from .user_input_manager import UserInputManager


def _build_path_tree(files: Iterable[CodeFile], git_root):
    tree = {}
    for file in files:
        path = os.path.relpath(file.path, git_root)
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


class CodeFileManager:
    def __init__(
        self,
        user_input_manager: UserInputManager,
        config: ConfigManager,
        code_context: CodeContext,
    ):
        self.user_input_manager = user_input_manager
        self.config = config
        self.code_context = code_context

        if self.code_context.files:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(self.config.git_root.name, "blue")
        _print_path_tree(
            _build_path_tree(self.code_context.files.values(), self.config.git_root),
            get_paths_with_git_diffs(self.config.git_root),
            self.config.git_root,
        )
        print()

    def _read_file(self, file: Union[str, CodeFile]) -> Iterable[str]:
        if isinstance(file, CodeFile):
            rel_path = file.path
        else:
            rel_path = self.config.git_root / file
        abs_path = self.config.git_root / rel_path

        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        return lines

    def _read_all_file_lines(self) -> None:
        self.file_lines = dict()
        for file in self.code_context.files.values():
            rel_path = os.path.relpath(file.path, self.config.git_root)
            # here keys are str not path object
            self.file_lines[rel_path] = self._read_file(file)

    def get_code_message(self):
        self._read_all_file_lines()
        code_message = ["Code Files:\n"]
        for file in self.code_context.files.values():
            abs_path = file.path
            rel_path = os.path.relpath(abs_path, self.config.git_root)

            # We always want to give GPT posix paths
            posix_rel_path = Path(rel_path).as_posix()
            code_message.append(posix_rel_path)

            for i, line in enumerate(self.file_lines[rel_path], start=1):
                if file.contains_line(i):
                    code_message.append(f"{i}:{line}")
            code_message.append("")

            git_diff_output = get_git_diff_for_path(self.config.git_root, rel_path)
            if git_diff_output:
                code_message.append("Current git diff for this file:")
                code_message.append(f"{git_diff_output}")

        return "\n".join(code_message)

    def _handle_delete(self, delete_change):
        file_path = self.config.git_root / delete_change.file
        if not file_path.exists():
            logging.error(f"Path {file_path} non-existent on delete")
            return

        cprint(f"Are you sure you want to delete {delete_change.file}?", "red")
        if self.user_input_manager.ask_yes_no(default_yes=False):
            logging.info(f"Deleting file {file_path}")
            cprint(f"Deleting {delete_change.file}...")
            if file_path in self.code_context.files:
                del self.code_context.files[file_path]
            file_path.unlink()
        else:
            cprint(f"Not deleting {delete_change.file}")

    def _get_new_code_lines(self, changes) -> Iterable[str] | None:
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

        rel_path = str(changes[0].file)
        new_code_lines = self.file_lines[rel_path].copy()
        if new_code_lines != self._read_file(rel_path):
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
                raise MentatError(f"Change line number overlap in file {change.file}")
            min_changed_line = change.first_changed_line
            new_code_lines = change.apply(new_code_lines)
        return new_code_lines

    def write_changes_to_files(self, code_changes: list[CodeChange]) -> None:
        files_to_write = dict()
        file_changes = defaultdict(list)
        for code_change in code_changes:
            # here keys are str not path object
            rel_path = str(code_change.file)
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
            file_path = self.config.git_root / rel_path
            if file_path not in self.code_context.files:
                # newly created files added to Mentat's context
                logging.info(f"Adding new file {file_path} to context")
                self.code_context.files[file_path] = CodeFile(file_path)
                # create any missing directories in the path
                file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w") as f:
                f.write("\n".join(code_lines))
