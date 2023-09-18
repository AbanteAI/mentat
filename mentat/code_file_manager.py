import logging
import os
from pathlib import Path
from typing import Union

from termcolor import cprint

from mentat.parsers.file_edit import FileEdit

from .code_context import CodeContext
from .code_file import CodeFile
from .config_manager import ConfigManager
from .errors import MentatError
from .git_handler import get_git_diff_for_path
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

    def _read_all_file_lines(self) -> None:
        self.file_lines = dict[Path, list[str]]()
        for file in self.code_context.files.values():
            rel_path = Path(os.path.relpath(file.path, self.config.git_root))
            # here keys are str not path object
            self.file_lines[rel_path] = self.read_file(file)

    def get_code_message(self):
        self._read_all_file_lines()
        code_message = ["Code Files:\n"]
        for file in self.code_context.files.values():
            abs_path = file.path
            rel_path = Path(os.path.relpath(abs_path, self.config.git_root))

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

    def _add_file(self, abs_path: Path):
        logging.info(f"Adding new file {abs_path} to context")
        self.code_context.files[abs_path] = CodeFile(abs_path)
        # create any missing directories in the path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("")

    def _delete_file(self, abs_path: Path):
        logging.info(f"Deleting file {abs_path}")
        if abs_path in self.code_context.files:
            del self.code_context.files[abs_path]
        abs_path.unlink()

    # Mainly does checks on if file is in context, file exists, file is unchanged, etc.
    def write_changes_to_files(self, file_edits: list[FileEdit]):
        for file_edit in file_edits:
            if file_edit.is_creation:
                if file_edit.file_path.exists():
                    raise MentatError(
                        f"Model attempted to create file {file_edit.file_path} which"
                        " already exists"
                    )
                self._add_file(file_edit.file_path)
            else:
                if file_edit.file_path not in self.code_context.files:
                    raise MentatError(
                        f"Attempted to edit file {file_edit.file_path} not in context"
                    )
                elif not file_edit.file_path.exists():
                    raise MentatError(
                        f"Attempted to edit non-existent file {file_edit.file_path}"
                    )

            if file_edit.is_deletion:
                cprint(f"Are you sure you want to delete {file_edit.file_path}?", "red")
                if self.user_input_manager.ask_yes_no(default_yes=False):
                    cprint(f"Deleting {file_edit.file_path}...", "red")
                    self._delete_file(file_edit.file_path)
                else:
                    cprint(f"Not deleting {file_edit.file_path}", "green")

            stored_lines = self.file_lines[file_edit.file_path]
            if stored_lines != self.read_file(file_edit.file_path):
                logging.info(
                    f"File '{file_edit.file_path}' changed while generating changes"
                )
                cprint(
                    f"File '{file_edit.file_path}' changed while generating; current"
                    " file changes will be erased. Continue?",
                    color="light_yellow",
                )
                if not self.user_input_manager.ask_yes_no(default_yes=False):
                    cprint(f"Not applying changes to file {file_edit.file_path}")

            if file_edit.rename_file_path is not None:
                self._add_file(file_edit.rename_file_path)
                self._delete_file(file_edit.file_path)
                file_edit.file_path = file_edit.rename_file_path

            new_lines = file_edit.get_file_lines(self)
            with open(file_edit.file_path) as f:
                f.write("\n".join(new_lines))
