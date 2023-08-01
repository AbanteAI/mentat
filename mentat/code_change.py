import os
from enum import Enum
from pathlib import Path

from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

from .model_error import ModelError


class CodeChangeAction(Enum):
    Insert = "insert"
    Replace = "replace"
    Delete = "delete"
    CreateFile = "create-file"
    DeleteFile = "delete-file"

    def has_surrounding_lines(self):
        return (
            self != CodeChangeAction.CreateFile and self != CodeChangeAction.DeleteFile
        )

    def has_removals(self):
        return (
            self == CodeChangeAction.Delete
            or self == CodeChangeAction.Replace
            or self == CodeChangeAction.DeleteFile
        )

    def has_additions(self):
        return (
            self == CodeChangeAction.Insert
            or self == CodeChangeAction.Replace
            or self == CodeChangeAction.CreateFile
        )


class CodeChange:
    def __init__(
        self,
        json_data: dict,
        code_lines: list[str],
        git_root: str,
        code_file_manager,
    ):
        self.json_data = json_data
        self.code_lines = code_lines
        self.first_changed_line = None
        self.file = Path(self.json_data["file"])
        self.first_changed_line = None
        self.last_changed_line = None
        self.git_root = git_root
        self.error = False
        try:
            self.lexer = get_lexer_for_filename(self.file)
            self.lexer.stripnl = False
            self.lexer.stripall = False
            self.lexer.ensurenl = False
        except ClassNotFound:
            self.lexer = TextLexer()

        try:
            self.action = CodeChangeAction(self.json_data["action"])
        except ValueError:
            raise ModelError(
                f"Model created change with unknown action {self.json_data['action']}",
                already_added_to_changelist=False,
            )

        try:
            match self.action:
                case CodeChangeAction.Insert:
                    if "insert-before-line" in self.json_data:
                        self.first_changed_line = self.json_data["insert-before-line"]
                        if "insert-after-line" in self.json_data:
                            if (
                                self.first_changed_line - 1
                                != self.json_data["insert-after-line"]
                            ):
                                self.error = "Insert line numbers invalid"
                    elif "insert-after-line" in self.json_data:
                        self.first_changed_line = (
                            self.json_data["insert-after-line"] + 1
                        )
                    else:
                        self.error = "Insert line number not specified"
                    self.first_changed_line -= 0.5
                    self.last_changed_line = self.first_changed_line

                case CodeChangeAction.Replace:
                    self.first_changed_line = self.json_data["start-line"]
                    self.last_changed_line = self.json_data["end-line"]

                case CodeChangeAction.Delete:
                    self.first_changed_line = self.json_data["start-line"]
                    self.last_changed_line = self.json_data["end-line"]
        except KeyError:
            self.error = "Line numbers not given"

        if (
            self.first_changed_line
            and self.last_changed_line
            and self.first_changed_line > self.last_changed_line
        ):
            self.error = "Starting line of change is greater than ending line of change"

        if self.action != CodeChangeAction.CreateFile:
            file_path = os.path.join(self.git_root, self.file)
            try:
                self.file_lines = code_file_manager.file_lines[file_path]
                self.line_number_buffer = len(str(len(self.file_lines) + 1)) + 1
            except KeyError:
                self.error = (
                    f"Model attempted to edit {file_path}, which isn't in current"
                    " context or doesn't exist"
                )
        else:
            if os.path.exists(self.file):
                self.error = (
                    f"Model attempted to create file that already exists: {self.file}"
                )

            self.file_lines = []
            self.line_number_buffer = 2

    def __lt__(self, other):
        return self.last_changed_line < other.last_changed_line

    def apply(self, cur_file_lines: list[str]) -> list[str]:
        match self.action:
            case CodeChangeAction.Insert:
                previous_lines = cur_file_lines[: int(self.first_changed_line)]
                following_lines = cur_file_lines[int(self.first_changed_line) :]
                new_file_lines = previous_lines + self.code_lines + following_lines

            case CodeChangeAction.Replace:
                previous_lines = cur_file_lines[: self.first_changed_line - 1]
                following_lines = cur_file_lines[self.last_changed_line :]
                new_file_lines = previous_lines + self.code_lines + following_lines

            case CodeChangeAction.Delete:
                previous_lines = cur_file_lines[: self.first_changed_line - 1]
                following_lines = cur_file_lines[self.last_changed_line :]
                new_file_lines = previous_lines + following_lines

            case CodeChangeAction.CreateFile | CodeChangeAction.DeleteFile:
                raise Exception(
                    f"CodeChange with action={self.action} shouldn't have apply called"
                )

        return new_file_lines
