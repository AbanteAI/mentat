from __future__ import annotations

import os
from pathlib import Path

import attr

from mentat.errors import MentatError
from mentat.parsers.change_display_helper import (
    DisplayInformation,
    FileActionType,
    change_delimiter,
    get_full_change,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no


# TODO: Add 'owner' to Replacement so that interactive mode can accept/reject multiple replacements at once
@attr.define(order=False)
class Replacement:
    """
    Represents that the lines from starting_line (inclusive) to ending_line (exclusive)
    should be replaced with new_lines
    """

    # Inclusive
    starting_line: int = attr.field()
    # Exclusive
    ending_line: int = attr.field()

    new_lines: list[str] = attr.field()

    def __lt__(self, other: Replacement):
        return self.ending_line < other.ending_line or (
            self.ending_line == other.ending_line
            and self.starting_line < other.ending_line
        )


async def _ask_user_change(
    display_information: DisplayInformation,
    text: str,
) -> bool:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    stream.send(get_full_change(display_information))
    stream.send(text, color="light_blue")
    return await ask_yes_no(default_yes=True)


@attr.define
class FileEdit:
    """
    Represents that this file_path content should have specified Replacements applied to it.
    Can also represent that this file should be created, deleted, or is being renamed.
    """

    # Should be abs path
    file_path: Path = attr.field()
    replacements: list[Replacement] = attr.field(factory=list)
    is_creation: bool = attr.field(default=False)
    is_deletion: bool = attr.field(default=False)
    # Should be abs path
    rename_file_path: Path | None = attr.field(default=None)

    def is_valid(self) -> bool:
        session_context = SESSION_CONTEXT.get()
        git_root = session_context.git_root
        stream = session_context.stream
        code_context = session_context.code_context

        rel_path = Path(os.path.relpath(self.file_path, git_root))
        if self.is_creation:
            if self.file_path.exists():
                stream.send(
                    f"File {rel_path} already exists, canceling creation.",
                    color="light_yellow",
                )
                return False
        else:
            if not self.file_path.exists():
                stream.send(
                    f"File {rel_path} does not exist, canceling all edits to file.",
                    color="light_yellow",
                )
                return False
            file_features_in_context = [
                f for f in code_context.features if f.path == self.file_path
            ] or code_context.include_files.get(self.file_path, [])
            if not all(
                any(f.contains_line(i) for f in file_features_in_context)
                for r in self.replacements
                for i in range(r.starting_line, r.ending_line)
            ):
                stream.send(
                    f"Edits to {rel_path} include lines not in context, "
                    "canceling all edits to file.",
                    color="light_yellow",
                )
                return False

        if self.rename_file_path is not None and self.rename_file_path.exists():
            rel_rename_path = Path(os.path.relpath(self.rename_file_path, git_root))
            stream.send(
                f"File {rel_path} being renamed to existing file {rel_rename_path},"
                " canceling rename.",
                color="light_yellow",
            )
            self.rename_file_path = None
        return True

    async def filter_replacements(
        self,
    ) -> bool:
        session_context = SESSION_CONTEXT.get()
        git_root = session_context.git_root
        code_file_manager = session_context.code_file_manager

        if self.is_creation:
            display_information = DisplayInformation(
                self.file_path, [], [], [], FileActionType.CreateFile
            )
            if not await _ask_user_change(display_information, "Create this file?"):
                return False
            file_lines = []
        else:
            rel_path = Path(os.path.relpath(self.file_path, git_root))
            file_lines = code_file_manager.file_lines[rel_path]

        if self.is_deletion:
            display_information = DisplayInformation(
                self.file_path, [], [], file_lines, FileActionType.DeleteFile
            )
            if not await _ask_user_change(display_information, "Delete this file?"):
                return False

        if self.rename_file_path is not None:
            display_information = DisplayInformation(
                self.file_path,
                [],
                [],
                [],
                FileActionType.RenameFile,
                new_name=self.rename_file_path,
            )
            if not await _ask_user_change(display_information, "Rename this file?"):
                self.rename_file_path = None

        new_replacements = list[Replacement]()
        for replacement in self.replacements:
            removed_block = file_lines[
                replacement.starting_line : replacement.ending_line
            ]
            display_information = DisplayInformation(
                self.file_path,
                file_lines,
                replacement.new_lines,
                removed_block,
                FileActionType.UpdateFile,
                replacement.starting_line,
                replacement.ending_line,
                self.rename_file_path,
            )
            if await _ask_user_change(display_information, "Keep this change?"):
                new_replacements.append(replacement)
        self.replacements = new_replacements

        return (
            self.is_creation
            or self.is_deletion
            or (self.rename_file_path is not None)
            or len(self.replacements) > 0
        )

    def _print_resolution(self, first: Replacement, second: Replacement):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        stream.send("Change overlap detected, auto-merged back to back changes:\n")
        stream.send(self.file_path)
        stream.send(change_delimiter)
        for line in first.new_lines + second.new_lines:
            stream.send("+ " + line, color="green")
        stream.send("")

    def resolve_conflicts(self):
        self.replacements.sort(reverse=True)
        for index, replacement in enumerate(self.replacements):
            for other in self.replacements[index + 1 :]:
                if (
                    other.ending_line > replacement.starting_line
                    and other.starting_line < replacement.ending_line
                ):
                    # Overlap conflict
                    other.ending_line = replacement.starting_line
                    other.starting_line = min(other.starting_line, other.ending_line)
                    self._print_resolution(other, replacement)
                elif (
                    other.ending_line == other.starting_line
                    and replacement.ending_line == replacement.starting_line
                    and replacement.starting_line == other.starting_line
                ):
                    # Insertion conflict
                    # This will be a bit wonky if there are more than 2 insertion conflicts on the same line
                    self._print_resolution(replacement, other)

    def get_updated_file_lines(self, file_lines: list[str]):
        self.replacements.sort(reverse=True)
        earliest_line = None
        for replacement in self.replacements:
            if earliest_line is not None and replacement.ending_line > earliest_line:
                # This should never happen if resolve conflicts is called
                raise MentatError("Error: Line overlap in Replacements")
            if replacement.ending_line > len(file_lines):
                file_lines += [""] * (replacement.ending_line - len(file_lines))
            earliest_line = replacement.starting_line
            file_lines = (
                file_lines[: replacement.starting_line]
                + replacement.new_lines
                + file_lines[replacement.ending_line :]
            )
        return file_lines
