import logging
from functools import cmp_to_key
from pathlib import Path
from typing import cast

import attr
from termcolor import cprint

from mentat.code_context import CodeContext
from mentat.code_file import CodeFile
from mentat.errors import MentatError
from mentat.user_input_manager import UserInputManager


@attr.s
class Addition:
    # Will insert directly before this line, 0 indexed
    line_number: int = attr.field()
    content: list[str] = attr.field()
    owner: int = attr.field()


@attr.s
class Deletion:
    # Inclusive, 0 indexed
    starting_line: int = attr.field()
    # Exclusive, 0 indexed
    ending_line: int = attr.field()
    owner: int = attr.field()


@attr.s
class Rename:
    # None represents deleting this file
    name: Path | None = attr.field()
    owner: int = attr.field()


AbstractSubChange = Addition | Deletion | Rename


def subchange_order(sub_1: AbstractSubChange, sub_2: AbstractSubChange) -> int:
    l1: int | None = None
    if type(sub_1) == Addition:
        l1 = sub_1.line_number
    elif type(sub_1) == Deletion:
        l1 = sub_1.ending_line

    l2: int | None = None
    if type(sub_2) == Addition:
        l2 = sub_2.line_number
    elif type(sub_2) == Deletion:
        l2 = sub_2.ending_line

    if l1 is None or l2 is None:
        return 0 if l1 == l2 else 1 if l1 is None else -1
    else:
        return 0 if l1 == l2 else 1 if l1 > l2 else -1


class AbstractChange:
    def __init__(self, file_path: Path | None, changes: list[AbstractSubChange]):
        """
        Creates a new AbstractChange for the given file with the given changes.
        The changes will be applied from the end of the file to the start.
        Multiple Additions on the same line will give the first Addition in the list priority;
        this will place it's content later in the file than the other Additions
        A Rename with name = None is a deletion, and a Rename when file_path is None is a file creation.
        """

        self.file_path = file_path
        self.changes = sorted(
            self._fix_changes(changes),
            reverse=True,
            key=cmp_to_key(subchange_order),
        )

    def _fix_changes(self, changes: list[AbstractSubChange]):
        deletions = [change for change in changes if type(change) == Deletion]
        additions = [change for change in changes if type(change) == Addition]
        renames = [change for change in changes if type(change) == Rename]

        # Remove all overlapping parts of Deletions
        deletions.sort(reverse=True, key=lambda change: change.ending_line)
        cur_start = None
        new_deletions = list[Deletion]()
        for deletion in deletions:
            if cur_start is None:
                cur_start = deletion.starting_line
            elif deletion.ending_line > cur_start:
                deletion.ending_line = cur_start
            cur_start = min(cur_start, deletion.starting_line)
            # If a Deletion no longer removes any lines, don't keep it
            if deletion.ending_line > deletion.starting_line:
                new_deletions.append(deletion)
        deletions = new_deletions

        # Shift all Additions to the front of Deletions
        additions.sort(reverse=True, key=lambda change: change.line_number)
        cur_deletion = 0
        cur_addition = 0
        while cur_addition < len(additions):
            while (
                cur_deletion < len(deletions)
                and deletions[cur_deletion].starting_line
                >= additions[cur_addition].line_number
            ):
                cur_deletion += 1
            if cur_deletion == len(deletions):
                break

            while (
                cur_addition < len(additions)
                and additions[cur_addition].line_number
                > deletions[cur_deletion].ending_line
            ):
                cur_addition += 1
            if cur_addition == len(additions):
                break

            if (
                additions[cur_addition].line_number
                > deletions[cur_deletion].starting_line
                and additions[cur_addition].line_number
                <= deletions[cur_deletion].ending_line
            ):
                additions[cur_addition].line_number = deletions[
                    cur_deletion
                ].starting_line

        return additions + deletions + renames

    def apply(
        self,
        code_lines: list[str],
        code_context: CodeContext,
        user_input_manager: UserInputManager,
    ):
        for subchange in self.changes:
            if type(subchange) == Rename:
                self._apply_rename(subchange, code_context, user_input_manager)
            elif type(subchange) == Addition:
                code_lines = self._apply_addition(subchange, code_lines, code_context)
            elif type(subchange) == Deletion:
                code_lines = self._apply_deletion(subchange, code_lines, code_context)
        return code_lines

    def _apply_rename(
        self,
        subchange: Rename,
        code_context: CodeContext,
        user_input_manager: UserInputManager,
    ):
        if subchange.name is None and self.file_path is None:
            raise MentatError("Attempted to delete file with no name")
        # Deleting a file?
        elif subchange.name is None:
            # pyright doesn't recognize that the previous if statement type guards self.file_path
            abs_path = code_context.config.git_root / cast(Path, self.file_path)
            if not abs_path.exists():
                logging.error(f"Path {abs_path} non-existent on delete")
                return
            cprint(f"Are you sure you want to delete {self.file_path}?", "red")
            if user_input_manager.ask_yes_no(default_yes=False):
                cprint(f"Deleting {self.file_path}...")
                self._delete_file(abs_path, code_context)
            else:
                cprint(f"Not deleting {self.file_path}")
                return
        # Creating a new file?
        elif self.file_path is None:
            abs_path = code_context.config.git_root / subchange.name
            if abs_path.exists():
                logging.error(f"Tried to create file {abs_path} which already exists")
                return
            cprint(f"Creating new file {subchange.name}", color="light_green")
            self._create_file(abs_path, code_context)
        # Renaming a file?
        else:
            orig_abs_path = code_context.config.git_root / self.file_path
            new_abs_path = code_context.config.git_root / subchange.name
            if not orig_abs_path.exists():
                raise MentatError(
                    f"Tried to rename file {orig_abs_path} does not exist"
                )
            if new_abs_path.exists():
                logging.error(
                    f"Tried to rename file to {new_abs_path} which already exists"
                )
                return
            self._delete_file(orig_abs_path, code_context)
            self._create_file(new_abs_path, code_context)
        self.file_path = subchange.name

    def _apply_addition(
        self, subchange: Addition, code_lines: list[str], code_context: CodeContext
    ):
        code_lines += [""] * (max(0, subchange.line_number - len(code_lines)))
        code_lines = (
            code_lines[: subchange.line_number]
            + subchange.content
            + code_lines[subchange.line_number :]
        )
        return code_lines

    def _apply_deletion(
        self, subchange: Deletion, code_lines: list[str], code_context: CodeContext
    ):
        subchange.ending_line = min(subchange.ending_line, len(code_lines))
        if subchange.ending_line > subchange.starting_line:
            code_lines = (
                code_lines[: subchange.starting_line]
                + code_lines[subchange.ending_line :]
            )
        return code_lines

    def _create_file(self, abs_path: Path, code_context: CodeContext):
        logging.info(f"Adding new file {abs_path} to context")
        code_context.files[abs_path] = CodeFile(abs_path)
        # create any missing directories in the path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("")

    def _delete_file(self, abs_path: Path, code_context: CodeContext):
        logging.info(f"Deleting file {abs_path}")
        if abs_path in code_context.files:
            del code_context.files[abs_path]
        abs_path.unlink()
