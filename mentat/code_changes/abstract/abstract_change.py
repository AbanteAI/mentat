from functools import cmp_to_key
from pathlib import Path

import attr


@attr.s
class Addition:
    # Will insert directly before this line, 0 indexed
    line_number: int = attr.field()
    content: str = attr.field()
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
    name: str | None = attr.field()
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
    def __init__(self, file_path: Path, changes: list[AbstractSubChange]):
        """
        Creates a new AbstractChange for the given file with the given changes.
        The changes will be applied from the end of the file to the start.
        Multiple Additions on the same line will give the first Addition in the list priority.
        A Rename with name = None is a deletion, and a Rename when file_path is None is a file creation.
        """
        self.file_path = file_path

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
        while True:
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

        self.changes = sorted(
            deletions + additions + renames,
            reverse=True,
            key=cmp_to_key(subchange_order),
        )
