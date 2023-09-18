# This file is mainly kept as legacy so that we don't have to rewrite this code

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mentat.config_manager import ConfigManager
from mentat.errors import ModelError
from mentat.parsers.change_display_helper import DisplayInformation, FileActionType
from mentat.parsers.file_edit import FileEdit, Replacement

if TYPE_CHECKING:
    # This normally will cause a circular import
    from mentat.code_file_manager import CodeFileManager


class OriginalFormatChangeAction(Enum):
    Insert = "insert"
    Replace = "replace"
    Delete = "delete"
    CreateFile = "create-file"
    DeleteFile = "delete-file"
    RenameFile = "rename-file"

    def has_surrounding_lines(self):
        return (
            self != OriginalFormatChangeAction.CreateFile
            and self != OriginalFormatChangeAction.DeleteFile
            and self != OriginalFormatChangeAction.RenameFile
        )

    def has_removals(self):
        return (
            self == OriginalFormatChangeAction.Delete
            or self == OriginalFormatChangeAction.Replace
            or self == OriginalFormatChangeAction.DeleteFile
        )

    def has_additions(self):
        return (
            self == OriginalFormatChangeAction.Insert
            or self == OriginalFormatChangeAction.Replace
            or self == OriginalFormatChangeAction.CreateFile
        )

    def get_file_action_type(self):
        match self:
            case OriginalFormatChangeAction.CreateFile:
                return FileActionType.CreateFile
            case OriginalFormatChangeAction.DeleteFile:
                return FileActionType.DeleteFile
            case OriginalFormatChangeAction.RenameFile:
                return FileActionType.RenameFile
            case _:
                return FileActionType.UpdateFile


class OriginalFormatChange:
    @classmethod
    def to_file_edits(
        cls,
        changes: list[OriginalFormatChange],
        config: ConfigManager,
    ) -> list[FileEdit]:
        file_edits = dict[Path, FileEdit]()
        for code_change in changes:
            rel_path = code_change.file
            abs_path = config.git_root / rel_path
            if abs_path not in file_edits:
                file_edits[abs_path] = FileEdit(abs_path, [])
            match code_change.action:
                case OriginalFormatChangeAction.CreateFile:
                    file_edits[abs_path].replacements.append(
                        Replacement(code_change.code_lines, 0, 0)
                    )
                    file_edits[abs_path].is_creation = True
                case OriginalFormatChangeAction.DeleteFile:
                    file_edits[abs_path].is_deletion = True
                case OriginalFormatChangeAction.RenameFile:
                    abs_new_path = config.git_root / code_change.name
                    file_edits[abs_path].rename_file_path = abs_new_path
                case _:
                    file_edits[abs_path].replacements.append(
                        Replacement(
                            code_change.code_lines,
                            code_change.first_changed_line,
                            code_change.last_changed_line,
                        )
                    )
        return [file_edit for file_edit in file_edits.values()]

    def __init__(
        self,
        json_data: dict[Any, Any],
        code_lines: list[str],
        code_file_manager: CodeFileManager,
        rename_map: dict[Path, Path] = {},
    ):
        self.json_data = json_data
        # Sometimes GPT puts quotes around numbers, so we have to convert those
        for json_key in [
            "insert-before-line",
            "insert-after-line",
            "start-line",
            "end-line",
        ]:
            if json_key in self.json_data:
                self.json_data[json_key] = int(self.json_data[json_key])
        self.code_lines = code_lines
        self.file = Path(self.json_data["file"])
        # This rename_map is a bit hacky; it shouldn't be used outside of streaming/parsing
        if self.file in rename_map:
            self.file = rename_map[self.file]
        self.first_changed_line: int = 0
        self.last_changed_line: int = 0
        self.error = ""

        try:
            self.action = OriginalFormatChangeAction(self.json_data["action"])
        except ValueError:
            raise ModelError(
                f"Model created change with unknown action {self.json_data['action']}",
                already_added_to_changelist=False,
            )

        try:
            match self.action:
                case OriginalFormatChangeAction.Insert:
                    if "insert-before-line" in self.json_data:
                        self.first_changed_line = (
                            self.json_data["insert-before-line"] - 1
                        )
                        if (
                            "insert-after-line" in self.json_data
                            and self.first_changed_line
                            != self.json_data["insert-after-line"]
                        ):
                            self.error = "Insert line numbers invalid"
                    elif "insert-after-line" in self.json_data:
                        self.first_changed_line = self.json_data["insert-after-line"]
                    else:
                        self.first_changed_line = 0
                        self.error = "Insert line number not specified"
                    self.last_changed_line = self.first_changed_line

                case OriginalFormatChangeAction.Replace:
                    self.first_changed_line = self.json_data["start-line"] - 1
                    self.last_changed_line = self.json_data["end-line"]

                case OriginalFormatChangeAction.Delete:
                    self.first_changed_line = self.json_data["start-line"] - 1
                    self.last_changed_line = self.json_data["end-line"]

                case OriginalFormatChangeAction.RenameFile:
                    self.name = Path(self.json_data["name"])

                case _:
                    pass

        except KeyError:
            self.error = "Line numbers not given"

        if (
            self.first_changed_line
            and self.last_changed_line
            and self.first_changed_line > self.last_changed_line
        ):
            self.error = "Starting line of change is greater than ending line of change"

        if self.action == OriginalFormatChangeAction.CreateFile:
            if self.file.exists():
                self.error = (
                    f"Model attempted to create file that already exists: {self.file}"
                )
            self.file_lines = []
            self.line_number_buffer = 2
        else:
            if (
                self.action == OriginalFormatChangeAction.RenameFile
                and self.name.exists()
            ):
                self.error = (
                    f"Model attempted to rename file {self.file} to a file that"
                    f" already exists: {self.name}"
                )

            rel_path = self.file
            try:
                self.file_lines = code_file_manager.file_lines[rel_path]
            except KeyError:
                self.error = (
                    f"Model attempted to edit {rel_path}, which isn't in current"
                    " context or doesn't exist"
                )

    def get_change_display_information(self) -> DisplayInformation:
        removed_block = (
            self.file_lines
            if self.action == OriginalFormatChangeAction.DeleteFile
            else (
                self.file_lines[self.first_changed_line : self.last_changed_line + 1]
                if self.action.has_removals()
                else []
            )
        )
        display_information = DisplayInformation(
            self.file,
            self.file_lines,
            self.code_lines,
            removed_block,
            self.action.get_file_action_type(),
            self.first_changed_line,
            self.last_changed_line,
            self.name if self.action == OriginalFormatChangeAction.RenameFile else None,
        )
        return display_information
