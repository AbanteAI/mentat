import logging
import os
from pathlib import Path
from typing import Union

from termcolor import cprint

from mentat.llm_api import count_tokens, model_context_size
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

    def _read_all_file_lines(self) -> None:
        self.file_lines = dict[Path, list[str]]()
        for file in self.code_context.files.values():
            # self.file_lines is relative to git root
            rel_path = Path(os.path.relpath(file.path, self.config.git_root))
            self.file_lines[rel_path] = self.read_file(file)

    def get_code_message(self, model: str) -> str:
        code_message: list[str] = []
        if self.code_context.diff_context.files:
            code_message += [
                "Diff References:",
                f' "-" = {self.code_context.diff_context.name}',
                ' "+" = Active Changes',
                "",
            ]

        self._read_all_file_lines()
        code_message += ["Code Files:\n"]
        for file in self.code_context.files.values():
            file_message: list[str] = []
            abs_path = file.path
            rel_path = Path(os.path.relpath(abs_path, self.config.git_root))

            # We always want to give GPT posix paths
            posix_rel_path = Path(rel_path).as_posix()
            file_message.append(posix_rel_path)

            for i, line in enumerate(self.file_lines[rel_path], start=1):
                if file.contains_line(i):
                    file_message.append(f"{i}:{line}")
            file_message.append("")

            if rel_path in self.code_context.diff_context.files:
                file_message = self.code_context.diff_context.annotate_file_message(
                    rel_path, file_message
                )

            code_message += file_message

        if self.code_context.code_map is not None:
            code_message_tokens = count_tokens("\n".join(code_message), model)
            context_size = model_context_size(model)
            if context_size:
                max_tokens_for_code_map = context_size - code_message_tokens
                if self.code_context.code_map.token_limit:
                    code_map_message_token_limit = min(
                        self.code_context.code_map.token_limit, max_tokens_for_code_map
                    )
                else:
                    code_map_message_token_limit = max_tokens_for_code_map
            else:
                code_map_message_token_limit = self.code_context.code_map.token_limit

            code_map_message = self.code_context.code_map.get_message(
                token_limit=code_map_message_token_limit
            )
            if code_map_message:
                match (code_map_message.level):
                    case "signatures":
                        cprint_message_level = "full syntax tree"
                    case "no_signatures":
                        cprint_message_level = "partial syntax tree"
                    case "filenames":
                        cprint_message_level = "filepaths only"

                cprint_message = f"\nIncluding CodeMap ({cprint_message_level})"
                cprint(cprint_message, color="green")
                code_message += f"\n{code_map_message}"
            else:
                cprint_message = [
                    "\nExcluding CodeMap from system message.",
                    "Reason: not enough tokens available in model context.",
                ]
                cprint_message = "\n".join(cprint_message)
                cprint(cprint_message, color="yellow")

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
                elif file_edit.file_path not in self.code_context.files:
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
                stored_lines = self.file_lines[rel_path]
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

            new_lines = file_edit.get_file_lines(stored_lines)
            with open(file_edit.file_path, "w") as f:
                f.write("\n".join(new_lines))
