import os
from pathlib import Path
from typing import Optional

import attr
from termcolor import colored

from mentat.errors import HistoryError
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.session_context import SESSION_CONTEXT


# All paths should be abs paths
@attr.define()
class RenameAction:
    old_file_name: Path = attr.field()
    cur_file_name: Path = attr.field()

    def undo(self) -> FileEdit:
        if self.old_file_name.exists():
            raise HistoryError(
                f"File {self.old_file_name} already exists; unable to undo rename from"
                f" {self.cur_file_name}"
            )
        else:
            os.rename(self.cur_file_name, self.old_file_name)
            return FileEdit(
                file_path=self.old_file_name, rename_file_path=self.cur_file_name
            )


@attr.define()
class CreationAction:
    cur_file_name: Path = attr.field()

    def undo(self) -> FileEdit:
        if not self.cur_file_name.exists():
            raise HistoryError(
                f"File {self.cur_file_name} does not exist; unable to delete"
            )
        else:
            self.cur_file_name.unlink()
            return FileEdit(file_path=self.cur_file_name, is_creation=True)


@attr.define()
class DeletionAction:
    old_file_name: Path = attr.field()
    old_file_lines: list[str] = attr.field()

    def undo(self) -> FileEdit:
        if self.old_file_name.exists():
            raise HistoryError(
                f"File {self.old_file_name} already exists; unable to re-create"
            )
        else:
            with open(self.old_file_name, "w") as f:
                f.write("\n".join(self.old_file_lines))
            return FileEdit(file_path=self.old_file_name, is_deletion=True)


@attr.define()
class EditAction:
    cur_file_name: Path = attr.field()
    old_file_lines: list[str] = attr.field()

    def undo(self) -> FileEdit:
        if not self.cur_file_name.exists():
            raise HistoryError(
                f"File {self.cur_file_name} does not exist; unable to undo edit"
            )
        else:
            new_file_lines = self.cur_file_name.read_text().split("\n")
            with open(self.cur_file_name, "w") as f:
                f.write("\n".join(self.old_file_lines))
            return FileEdit(
                file_path=self.cur_file_name,
                replacements=[
                    Replacement(
                        starting_line=0,
                        ending_line=len(self.old_file_lines),
                        new_lines=new_file_lines,
                    )
                ],
            )


HistoryAction = RenameAction | CreationAction | DeletionAction | EditAction


# TODO: Keep track of when we create directories so we can undo those as well
class EditHistory:
    def __init__(self):
        self.edits = list[list[HistoryAction]]()
        self.cur_edit = list[HistoryAction]()
        self.undone_edits = list[list[FileEdit]]()

    def add_action(self, history_action: HistoryAction):
        self.cur_edit.append(history_action)

    def push_edits(self):
        if self.cur_edit:
            self.edits.append(self.cur_edit)
            self.cur_edit = list[HistoryAction]()

    def undo(self) -> str:
        if not self.edits:
            return colored("No edits available to undo", color="light_red")

        # Make sure to go top down
        cur_edit = self.edits.pop()
        errors = list[str]()
        undone_edit = list[FileEdit]()
        while cur_edit:
            cur_action = cur_edit.pop()
            try:
                redo_edit = cur_action.undo()
                undone_edit.append(redo_edit)
            except HistoryError as e:
                errors.append(colored(str(e), color="light_red"))
        if undone_edit:
            self.undone_edits.append(undone_edit)
        return "\n".join(errors)

    async def redo(self) -> Optional[str]:
        if not self.undone_edits:
            return colored("No edits available to redo", color="light_red")

        session_context = SESSION_CONTEXT.get()
        code_file_manager = session_context.code_file_manager

        edits_to_redo = self.undone_edits.pop()
        edits_to_redo.reverse()
        await code_file_manager.write_changes_to_files(edits_to_redo)

    def undo_all(self) -> str:
        if not self.edits:
            return colored("No edits available to undo", color="light_red")

        errors = list[str]()
        while self.edits:
            error = self.undo()
            if error:
                errors.append(error)
        return "\n".join(errors)
