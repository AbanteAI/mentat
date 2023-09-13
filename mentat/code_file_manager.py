import logging
import os
from pathlib import Path
from typing import Union

from termcolor import cprint

from mentat.code_changes.abstract.abstract_change import AbstractChange

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

    def _read_file(self, file: Union[Path, CodeFile]) -> list[str]:
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
            self.file_lines[rel_path] = self._read_file(file)

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

    def write_changes_to_files(self, code_changes: list[AbstractChange]) -> None:
        for change in code_changes:
            if change.file_path is not None:
                abs_path = self.config.git_root / change.file_path
                if abs_path not in self.code_context.files:
                    raise MentatError(
                        f"Attempted to edit file {abs_path} not in context"
                    )
                elif not abs_path.exists():
                    raise MentatError(f"Attempted to edit non-existent file {abs_path}")

                code_lines = self.file_lines[change.file_path].copy()
                if code_lines != self._read_file(change.file_path):
                    logging.info(
                        f"File '{change.file_path}' changed while generating changes"
                    )
                    cprint(
                        f"File '{change.file_path}' changed while generating; current"
                        " file changes will be erased. Continue?",
                        color="light_yellow",
                    )
                    if not self.user_input_manager.ask_yes_no(default_yes=False):
                        cprint(f"Not applying changes to file {change.file_path}")
            else:
                code_lines = []
            code_lines = change.apply(
                code_lines, self.code_context, self.user_input_manager
            )
            if change.file_path is not None:
                with open(change.file_path) as f:
                    f.write("\n".join(code_lines))
