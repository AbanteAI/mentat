from typing import Optional

from termcolor import colored

from mentat.errors import HistoryError
from mentat.parsers.file_edit import FileEdit
from mentat.session_context import SESSION_CONTEXT


# TODO: Keep track of when we create directories so we can undo those as well
class EditHistory:
    def __init__(self):
        self.edits = list[list[FileEdit]]()
        self.cur_edits = list[FileEdit]()
        self.undone_edits = list[list[FileEdit]]()

    def add_edit(self, file_edit: FileEdit):
        self.cur_edits.append(file_edit)

    def push_edits(self):
        if self.cur_edits:
            self.edits.append(self.cur_edits)
            self.cur_edits = list[FileEdit]()

    def undo(self) -> str:
        if not self.edits:
            return colored("No edits available to undo", color="light_red")

        # Make sure to go top down
        cur_edit = self.edits.pop()
        errors = list[str]()
        undone_edit = list[FileEdit]()
        while cur_edit:
            cur_file_edit = cur_edit.pop()
            try:
                cur_file_edit.undo()
                undone_edit.append(cur_file_edit)
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
        for edit in edits_to_redo:
            edit.display_full_edit(code_file_manager.file_lines[edit.file_path])
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
