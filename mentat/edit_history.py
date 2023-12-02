import os
from pathlib import Path

import attr
from termcolor import colored


# All paths should be abs paths
@attr.define()
class RenameAction:
    old_file_name: Path = attr.field()
    cur_file_name: Path = attr.field()

    def undo(self) -> str | None:
        if self.old_file_name.exists():
            return colored(
                f"File {self.old_file_name} already exists; unable to undo rename from"
                f" {self.cur_file_name}",
                color="light_red",
            )
        else:
            os.rename(self.cur_file_name, self.old_file_name)


@attr.define()
class CreationAction:
    cur_file_name: Path = attr.field()

    def undo(self) -> str | None:
        if not self.cur_file_name.exists():
            return colored(
                f"File {self.cur_file_name} does not exist; unable to delete",
                color="light_red",
            )
        else:
            self.cur_file_name.unlink()


@attr.define()
class DeletionAction:
    old_file_name: Path = attr.field()
    old_file_lines: list[str] = attr.field()

    def undo(self) -> str | None:
        if self.old_file_name.exists():
            return colored(
                f"File {self.old_file_name} already exists; unable to re-create",
                color="light_red",
            )
        else:
            with open(self.old_file_name, "w") as f:
                f.write("\n".join(self.old_file_lines))


@attr.define()
class EditAction:
    cur_file_name: Path = attr.field()
    old_file_lines: list[str] = attr.field()

    def undo(self) -> str | None:
        if not self.cur_file_name.exists():
            return colored(
                f"File {self.cur_file_name} does not exist; unable to undo edit",
                color="light_red",
            )
        else:
            with open(self.cur_file_name, "w") as f:
                f.write("\n".join(self.old_file_lines))


HistoryAction = RenameAction | CreationAction | DeletionAction | EditAction


# TODO: Keep track of when we create directories so we can undo those as well
class EditHistory:
    def __init__(self):
        self.edits = list[list[HistoryAction]]()
        self.cur_edit = list[HistoryAction]()

    def add_action(self, history_action: HistoryAction):
        self.cur_edit.append(history_action)

    def push_edits(self):
        if self.cur_edit:
            self.edits.append(self.cur_edit)
            self.cur_edit = list[HistoryAction]()

    # TODO: Add redo
    def undo(self) -> str:
        if not self.edits:
            return colored("No edits available to undo", color="light_red")

        # Make sure to go top down
        cur_edit = self.edits.pop()
        errors = list[str]()
        while cur_edit:
            cur_action = cur_edit.pop()
            error = cur_action.undo()
            if error is not None:
                errors.append(error)
        return "\n".join(errors)

    def undo_all(self) -> str:
        if not self.edits:
            return colored("No edits available to undo", color="light_red")

        errors = list[str]()
        while self.edits:
            error = self.undo()
            if error:
                errors.append(error)
        return "\n".join(errors)
