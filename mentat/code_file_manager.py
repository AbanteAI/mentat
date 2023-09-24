import logging
import os
from pathlib import Path
from typing import Union

from termcolor import cprint

from mentat.context_tree.file_node import FileNode
from mentat.parsers.file_edit import FileEdit

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

    def read_file(self, file: Union[Path, CodeFile]) -> list[str]:
        if isinstance(file, CodeFile):
            rel_path = file.path
        else:
            rel_path = file
        abs_path = self.config.git_root / rel_path

        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        return lines

    def file_lines(self, path: Path) -> list[str]:
        """Temporary helper func, to be handled in code_context directly by file_node"""
        node = self.code_context.root[path]
        if isinstance(node, FileNode):
            return node.path.read_text().split("\n")
        else:
            raise MentatError(f"Path {path} is not a file")

    def _add_file(self, abs_path: Path):
        logging.info(f"Adding new file {abs_path} to context")
        # create any missing directories in the path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("")

    def _delete_file(self, abs_path: Path):
        logging.info(f"Deleting file {abs_path}")
        abs_path.unlink()

    # Mainly does checks on if file is in context, file exists, file is unchanged, etc.
    def write_changes_to_files(self, file_edits: list[FileEdit]):
        for file_edit in file_edits:
            rel_path = Path(os.path.relpath(file_edit.file_path, self.config.git_root))
            if file_edit.is_creation:
                if file_edit.file_path.exists():
                    raise MentatError(
                        f"Model attempted to create file {file_edit.file_path} which"
                        " already exists"
                    )
                self._add_file(file_edit.file_path)
            else:
                if not file_edit.file_path.exists():
                    raise MentatError(
                        f"Attempted to edit non-existent file {file_edit.file_path}"
                    )
                elif rel_path not in self.code_context.files:
                    raise MentatError(
                        f"Attempted to edit file {file_edit.file_path} not in context"
                    )

            if file_edit.is_deletion:
                cprint(f"Are you sure you want to delete {rel_path}?", "red")
                if self.user_input_manager.ask_yes_no(default_yes=False):
                    cprint(f"Deleting {rel_path}...", "red")
                    self._delete_file(file_edit.file_path)
                    continue
                else:
                    cprint(f"Not deleting {rel_path}", "green")

            if not file_edit.is_creation:
                stored_lines = self.file_lines(rel_path)
                if stored_lines != self.read_file(rel_path):
                    logging.info(
                        f"File '{file_edit.file_path}' changed while generating changes"
                    )
                    cprint(
                        f"File '{rel_path}' changed while generating; current"
                        " file changes will be erased. Continue?",
                        color="light_yellow",
                    )
                    if not self.user_input_manager.ask_yes_no(default_yes=False):
                        cprint(f"Not applying changes to file {rel_path}")
            else:
                stored_lines = []

            if file_edit.rename_file_path is not None:
                if file_edit.rename_file_path.exists():
                    raise MentatError(
                        f"Attempted to rename file {file_edit.file_path} to existing"
                        f" file {file_edit.rename_file_path}"
                    )
                self._add_file(file_edit.rename_file_path)
                self._delete_file(file_edit.file_path)
                file_edit.file_path = file_edit.rename_file_path

            new_lines = file_edit.get_updated_file_lines(stored_lines)
            with open(file_edit.file_path, "w") as f:
                f.write("\n".join(new_lines))
