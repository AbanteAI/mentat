import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Union

from termcolor import cprint

from mentat.context_tree.file_node import FileNode

from .change_conflict_resolution import (
    resolve_insertion_conflicts,
    resolve_non_insertion_conflicts,
)
from .code_change import CodeChange, CodeChangeAction
from .code_context import CodeContext
from .code_file import CodeFile
from .config_manager import ConfigManager
from .errors import MentatError
from .user_input_manager import UserInputManager


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

    def _read_file(self, file: Union[Path, CodeFile]) -> list[str]:
        if isinstance(file, CodeFile):
            rel_path = file.path
        else:
            rel_path = file
        abs_path = self.config.git_root / rel_path

        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        return lines
    
    def file_lines(self, path: Path) -> list[str]:
        node = self.code_context.root[path]
        if isinstance(node, FileNode):
            return node.path.read_text().split("\n")
        else:
            raise MentatError(f"Path {path} is not a file")

    def _add_file(self, abs_path: Path):
        logging.info(f"Adding new file {abs_path} to context")
        # create any missing directories in the path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

    def _delete_file(self, abs_path: Path):
        logging.info(f"Deleting file {abs_path}")
        abs_path.unlink()

    def _handle_delete(self, delete_change: CodeChange):
        abs_path = self.config.git_root / delete_change.file
        if not abs_path.exists():
            logging.error(f"Path {abs_path} non-existent on delete")
            return

        cprint(f"Are you sure you want to delete {delete_change.file}?", "red")
        if self.user_input_manager.ask_yes_no(default_yes=False):
            cprint(f"Deleting {delete_change.file}...")
            self._delete_file(abs_path)
        else:
            cprint(f"Not deleting {delete_change.file}")

    def _get_new_code_lines(
        self, rel_path: Path, changes: list[CodeChange]
    ) -> list[str] | None:
        if not changes:
            return []
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

        new_code_lines = self.file_lines(rel_path)
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
        for change in changes:
            if change.last_changed_line >= min_changed_line:
                raise MentatError(f"Change line number overlap in file {change.file}")
            min_changed_line = change.first_changed_line
            new_code_lines = change.apply(new_code_lines)
        return new_code_lines

    def write_changes_to_files(self, code_changes: list[CodeChange]) -> None:
        file_changes = defaultdict[Path, list[CodeChange]](list)
        for code_change in code_changes:
            rel_path = code_change.file
            abs_path = self.config.git_root / rel_path
            match code_change.action:
                case CodeChangeAction.CreateFile:
                    cprint(f"Creating new file {rel_path}", color="light_green")
                    self._add_file(abs_path)
                    with open(abs_path, "w") as f:
                        f.write("\n".join(code_change.code_lines))
                case CodeChangeAction.DeleteFile:
                    self._handle_delete(code_change)
                case CodeChangeAction.RenameFile:
                    abs_new_path = self.config.git_root / code_change.name
                    self._add_file(abs_new_path)
                    code_lines = self.file_lines(rel_path)
                    with open(abs_new_path, "w") as f:
                        f.write("\n".join(code_lines))
                    self._delete_file(abs_path)
                    file_changes[code_change.name] += file_changes[rel_path]
                    file_changes[rel_path] = []
                case _:
                    file_changes[rel_path].append(code_change)

        for rel_path, changes in file_changes.items():
            abs_path = self.config.git_root / rel_path
            new_code_lines = self._get_new_code_lines(rel_path, changes)
            if new_code_lines:
                if abs_path not in self.code_context.files:
                    raise MentatError(
                        f"Attempted to edit file {abs_path} not in context"
                    )
                with open(abs_path, "w") as f:
                    f.write("\n".join(new_code_lines))

        self.code_context.refresh()
