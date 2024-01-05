from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from mentat.edit_history import EditHistory
from mentat.errors import MentatError
from mentat.interval import Interval
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import get_relative_path, sha256

if TYPE_CHECKING:
    # This normally will cause a circular import
    from mentat.parsers.file_edit import FileEdit


class CodeFileManager:
    def __init__(self):
        self.file_lines = dict[Path, list[str]]()
        self.history = EditHistory()

    def read_file(self, path: Path) -> list[str]:
        # TODO: Change to only ever using this function to read files, then cache files and
        # only re-read them when their last modified time is updated
        session_context = SESSION_CONTEXT.get()

        abs_path = path if path.is_absolute() else session_context.cwd / path
        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        self.file_lines[abs_path] = lines
        return lines

    def create_file(self, abs_path: Path, content: str = ""):
        ctx = SESSION_CONTEXT.get()
        code_context = ctx.code_context

        logging.info(f"Creating new file {abs_path}")
        # Create any missing directories in the path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)

        if abs_path not in code_context.include_files:
            code_context.include(abs_path)

    def delete_file(self, abs_path: Path):
        ctx = SESSION_CONTEXT.get()
        code_context = ctx.code_context

        logging.info(f"Deleting file {abs_path}")

        if abs_path in code_context.include_files:
            code_context.exclude(abs_path)
        abs_path.unlink()

    def rename_file(self, abs_path: Path, new_abs_path: Path):
        ctx = SESSION_CONTEXT.get()
        code_context = ctx.code_context

        logging.info(f"Renaming file {abs_path} to {new_abs_path}")
        if abs_path in code_context.include_files:
            code_context.exclude(abs_path)
        os.rename(abs_path, new_abs_path)
        if new_abs_path not in code_context.include_files:
            code_context.include(new_abs_path)

    # Mainly does checks on if file is in context, file exists, file is unchanged, etc.
    async def write_changes_to_files(
        self,
        file_edits: list[FileEdit],
    ) -> list[FileEdit]:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        agent_handler = session_context.agent_handler

        if not file_edits:
            return []

        applied_edits: list[FileEdit] = []
        for file_edit in file_edits:
            display_path = get_relative_path(file_edit.file_path, session_context.cwd)

            if file_edit.is_creation:
                if file_edit.file_path.exists():
                    raise MentatError(
                        f"Model attempted to create file {file_edit.file_path} which"
                        " already exists"
                    )
                self.create_file(file_edit.file_path)
            elif not file_edit.file_path.exists():
                raise MentatError(
                    f"Attempted to edit non-existent file {file_edit.file_path}"
                )

            if file_edit.is_deletion:
                stream.send(f"Deleting {display_path}...", style="error")
                # We use the current lines rather than the stored lines for undo
                file_edit.previous_file_lines = self.read_file(file_edit.file_path)
                self.delete_file(file_edit.file_path)
                applied_edits.append(file_edit)
                continue

            if not file_edit.is_creation:
                # TODO: We use read_file so much that this probably doesn't work anymore
                # We should instead make sure the last modified time doesn't change between code message and now
                stored_lines = self.file_lines[file_edit.file_path]
                if stored_lines != self.read_file(file_edit.file_path):
                    logging.info(
                        f"File '{file_edit.file_path}' changed while generating changes"
                    )
                    stream.send(
                        f"File '{display_path}' changed while"
                        " generating; current file changes will be erased. Continue?",
                        style="warning",
                    )
                    if not await ask_yes_no(default_yes=False):
                        stream.send(f"Not applying changes to file {display_path}")
                        continue
            else:
                stored_lines = []

            if file_edit.rename_file_path is not None:
                if file_edit.rename_file_path.exists():
                    raise MentatError(
                        f"Attempted to rename file {file_edit.file_path} to existing"
                        f" file {file_edit.rename_file_path}"
                    )
                self.rename_file(file_edit.file_path, file_edit.rename_file_path)

            new_lines = file_edit.get_updated_file_lines(stored_lines)
            if new_lines != stored_lines:
                file_path = file_edit.rename_file_path or file_edit.file_path
                # We use the current lines rather than the stored lines for undo
                file_edit.previous_file_lines = self.read_file(file_path)
                with open(file_path, "w") as f:
                    f.write("\n".join(new_lines))
            applied_edits.append(file_edit)

        for applied_edit in applied_edits:
            self.history.add_edit(applied_edit)
        if not agent_handler.agent_enabled:
            self.history.push_edits()
        return applied_edits

    def get_file_checksum(self, path: Path, interval: Interval | None = None) -> str:
        if path.is_dir():
            return ""  # TODO: Build and maintain a hash tree for git_root
        text = path.read_text()
        if interval is not None:
            lines = text.splitlines()
            filtered_lines = [
                line for i, line in enumerate(lines, start=1) if interval.contains(i)
            ]
            text = "\n".join(filtered_lines)
        return sha256(text)
