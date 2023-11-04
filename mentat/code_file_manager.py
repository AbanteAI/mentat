from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from mentat.edit_history import (
    CreationAction,
    DeletionAction,
    EditAction,
    EditHistory,
    RenameAction,
)
from mentat.errors import MentatError
from mentat.interval import Interval
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import sha256

if TYPE_CHECKING:
    # This normally will cause a circular import
    from mentat.code_context import CodeContext
    from mentat.parsers.file_edit import FileEdit


class CodeFileManager:
    def __init__(self):
        self.file_lines = dict[Path, list[str]]()
        self.history = EditHistory()

    def read_file(self, path: Path) -> list[str]:
        ctx = SESSION_CONTEXT.get()

        abs_path = path if path.is_absolute() else ctx.cwd.joinpath(path)
        rel_path = Path(os.path.relpath(abs_path, ctx.cwd))
        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        self.file_lines[rel_path] = lines
        return lines

    def _create_file(self, code_context: CodeContext, abs_path: Path):
        logging.info(f"Creating new file {abs_path}")
        # Create any missing directories in the path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as f:
            f.write("")
        code_context.include(abs_path)

    def _delete_file(self, code_context: CodeContext, abs_path: Path):
        logging.info(f"Deleting file {abs_path}")
        code_context.exclude(abs_path)
        abs_path.unlink()

    def _rename_file(self, code_context: CodeContext, abs_path: Path, new_abs_path: Path):
        logging.info(f"Renaming file {abs_path} to {new_abs_path}")
        os.rename(abs_path, new_abs_path)
        code_context.include(new_abs_path)
        code_context.include(abs_path)

    # Mainly does checks on if file is in context, file exists, file is unchanged, etc.
    async def write_changes_to_files(
        self,
        file_edits: list[FileEdit],
        code_context: CodeContext,
    ):
        ctx = SESSION_CONTEXT.get()

        for file_edit in file_edits:
            rel_path = Path(os.path.relpath(file_edit.file_path, ctx.cwd))
            if file_edit.is_creation:
                if file_edit.file_path.exists():
                    raise MentatError(f"Model attempted to create file {file_edit.file_path} which" " already exists")
                self.history.add_action(CreationAction(file_edit.file_path))
                self._create_file(code_context, file_edit.file_path)
            else:
                if not file_edit.file_path.exists():
                    raise MentatError(f"Attempted to edit non-existent file {file_edit.file_path}")
                context_features = code_context.features or code_context.include_files.values()
                missing_lines = False
                for r in file_edit.replacements:
                    for i in range(r.starting_line, r.ending_line):
                        if not any(f.contains_line(i) for f in context_features):
                            missing_lines = True
                if not context_features or missing_lines:
                    ctx.stream.send(
                        f"Attempted to edit file {file_edit.file_path} not in context",
                        color="yellow",
                    )
                    continue

            if file_edit.is_deletion:
                ctx.stream.send(f"Are you sure you want to delete {rel_path}?", color="red")
                if await ask_yes_no(default_yes=False):
                    ctx.stream.send(f"Deleting {rel_path}...", color="red")
                    # We use the current lines rather than the stored lines for undo
                    self.history.add_action(DeletionAction(file_edit.file_path, self.read_file(file_edit.file_path)))
                    self._delete_file(code_context, file_edit.file_path)
                    continue
                else:
                    ctx.stream.send(f"Not deleting {rel_path}", color="green")

            if not file_edit.is_creation:
                stored_lines = self.file_lines[rel_path]
                if stored_lines != self.read_file(file_edit.file_path):
                    logging.info(f"File '{file_edit.file_path}' changed while generating changes")
                    ctx.stream.send(
                        f"File '{rel_path}' changed while generating; current"
                        " file changes will be erased. Continue?",
                        color="light_yellow",
                    )
                    if not await ask_yes_no(default_yes=False):
                        ctx.stream.send(f"Not applying changes to file {rel_path}")
                        continue
            else:
                stored_lines = []

            if file_edit.rename_file_path is not None:
                if file_edit.rename_file_path.exists():
                    raise MentatError(
                        f"Attempted to rename file {file_edit.file_path} to existing"
                        f" file {file_edit.rename_file_path}"
                    )
                self.history.add_action(RenameAction(file_edit.file_path, file_edit.rename_file_path))
                self._rename_file(code_context, file_edit.file_path, file_edit.rename_file_path)
                file_edit.file_path = file_edit.rename_file_path

            new_lines = file_edit.get_updated_file_lines(stored_lines)
            if new_lines != stored_lines:
                # We use the current lines rather than the stored lines for undo
                self.history.add_action(EditAction(file_edit.file_path, self.read_file(file_edit.file_path)))
                with open(file_edit.file_path, "w") as f:
                    f.write("\n".join(new_lines))
        self.history.push_edits()

    def get_file_checksum(self, path: Path, intervals: list[Interval] | None = None) -> str:
        if path.is_dir():
            return ""  # TODO: Build and maintain a hash tree for git_root
        text = path.read_text()
        if intervals is not None:
            lines = text.splitlines()
            filtered_lines = [
                line for i, line in enumerate(lines, start=1) if any([interval.contains(i) for interval in intervals])
            ]
            text = "\n".join(filtered_lines)
        return sha256(text)
