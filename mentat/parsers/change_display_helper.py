from enum import Enum
from pathlib import Path
from typing import List, Tuple, cast

import attr
from pygments import lex
from pygments.formatters import TerminalFormatter
from pygments.lexer import Lexer
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

from mentat.parsers.streaming_printer import FormattedString
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path


def get_lexer(file_path: Path):
    try:
        lexer: Lexer = get_lexer_for_filename(file_path)
    except ClassNotFound:
        lexer = TextLexer()
    lexer.stripnl = False
    lexer.stripall = False
    lexer.ensurenl = False
    return lexer


def get_line_number_buffer(file_lines: list[str]):
    return 1


class FileActionType(Enum):
    RenameFile = "rename"
    CreateFile = "create"
    DeleteFile = "delete"
    UpdateFile = "update"


def get_file_action_type(is_creation: bool, is_deletion: bool, new_name: Path | None):
    if is_creation:
        file_action_type = FileActionType.CreateFile
    elif is_deletion:
        file_action_type = FileActionType.DeleteFile
    elif new_name is not None:
        file_action_type = FileActionType.RenameFile
    else:
        file_action_type = FileActionType.UpdateFile
    return file_action_type


@attr.define(slots=False)
class DisplayInformation:
    file_name: Path = attr.field()
    file_lines: list[str] = attr.field()
    added_block: list[str] = attr.field()
    removed_block: list[str] = attr.field()
    file_action_type: FileActionType = attr.field()
    first_changed_line: int = attr.field(default=0)
    last_changed_line: int = attr.field(default=0)
    new_name: Path | None = attr.field(default=None)

    def __attrs_post_init__(self):
        ctx = SESSION_CONTEXT.get()

        self.line_number_buffer = get_line_number_buffer(self.file_lines)
        self.lexer = get_lexer(self.file_name)

        if self.file_name.is_absolute():
            self.file_name = get_relative_path(self.file_name, ctx.cwd)
        if self.new_name is not None and self.new_name.is_absolute():
            self.new_name = get_relative_path(self.new_name, ctx.cwd)


def _remove_empty_lines(lines: list[str]) -> list[str]:
    if not lines:
        return []

    # Find the first non-empty line
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1

    # Find the last non-empty line
    end = len(lines) - 1
    while end > start and not lines[end].strip():
        end -= 1

    # If all lines are empty, return nothing
    if start == len(lines):
        return []

    # Return the list with no empty lines
    return lines[start : end + 1]


def _prefixed_lines(line_number_buffer: int, lines: list[str], prefix: str) -> str:
    return "\n".join([prefix + " " * (line_number_buffer - len(prefix)) + line.strip("\n") for line in lines])


def _get_code_block(
    code_lines: list[str],
    line_number_buffer: int,
    prefix: str,
    color: str | None,
) -> FormattedString:
    lines = _prefixed_lines(line_number_buffer, code_lines, prefix)
    if color is None:
        return lines
    else:
        return (lines, {"color": color})


def display_full_change(display_information: DisplayInformation, prefix: str = ""):
    ctx = SESSION_CONTEXT.get()

    full_change: List[FormattedString] = [
        get_file_name(display_information),
        ("=" * 60 if display_information.added_block or display_information.removed_block else ""),
        get_previous_lines(display_information),
        get_removed_lines(display_information),
        get_added_lines(display_information),
        get_later_lines(display_information),
        ("=" * 60 if display_information.added_block or display_information.removed_block else ""),
    ]
    # TODO: This is called by undo and redo; this is very hardcoded to terminalclient ui right now
    # (so it might look weird in vscode extension), but once we move commands to terminalclient we can remove this
    for line in full_change:
        if isinstance(line, str):
            if not line.strip():
                continue
            ctx.stream.send(prefix, end="")
            ctx.stream.send(f"\n{prefix}".join(line.split("\n")))
        elif isinstance(line, Tuple):
            if not line[0].strip():
                continue
            for sub_line in line[0].split("\n"):
                ctx.stream.send(prefix, end="")
                ctx.stream.send(sub_line, **line[1])
        else:
            ctx.stream.send(prefix, end="")
            for text in line:
                for i, sub_line in enumerate(text[0].split("\n")):
                    if i != 0:
                        ctx.stream.send(prefix, end="")
                    ctx.stream.send(sub_line, **text[1], end="")
                    if i != len(text[0].split("\n")) - 1:
                        ctx.stream.send("")
            ctx.stream.send("")


def get_file_name(
    display_information: DisplayInformation,
) -> FormattedString:
    match display_information.file_action_type:
        case FileActionType.CreateFile:
            return (f"\n{display_information.file_name}*", {"color": "bright_green"})
        case FileActionType.DeleteFile:
            return (
                f"\nDeletion: {display_information.file_name}",
                {"color": "bright_red"},
            )
        case FileActionType.RenameFile:
            return (
                (f"\nRename: {display_information.file_name} ->" f" {display_information.new_name}"),
                {"color": "yellow"},
            )
        case FileActionType.UpdateFile:
            return (f"\n{display_information.file_name}", {"color": "bright_blue"})


def get_file_name_display(display_information: DisplayInformation):
    match display_information.file_action_type:
        case FileActionType.CreateFile:
            return (f"{display_information.file_name}*", "creation")
        case FileActionType.DeleteFile:
            return (
                f"Deletion: {display_information.file_name}",
                "deletion",
            )
        case FileActionType.RenameFile:
            return (
                (f"Rename: {display_information.file_name} ->" f" {display_information.new_name}"),
                "rename",
            )
        case FileActionType.UpdateFile:
            return (f"{display_information.file_name}", "edit")


def get_added_lines(
    display_information: DisplayInformation,
    prefix: str = "+",
    color: str | None = "green",
) -> FormattedString:
    return _get_code_block(
        display_information.added_block,
        display_information.line_number_buffer,
        prefix,
        color,
    )


def get_removed_lines(
    display_information: DisplayInformation,
    prefix: str = "-",
    color: str | None = "red",
) -> FormattedString:
    return _get_code_block(
        display_information.removed_block,
        display_information.line_number_buffer,
        prefix,
        color,
    )


def highlight_text(text: str, lexer: Lexer) -> FormattedString:
    formatter = TerminalFormatter(bg="dark")  # type: ignore
    string: FormattedString = []
    for ttype, value in lex(text, lexer):
        # We use TerminalFormatter's color scheme; TODO: Hook this up to our style themes instead
        color = cast(str, formatter._get_color(ttype))  # type: ignore

        # Convert Pygment styles to Rich styles
        if color.startswith("*"):
            # TODO: Send bold style
            color = color[1:-1]
        if color.startswith("_"):
            # TODO: Send italic style
            color = color[1:-1]
        if color.startswith("bright"):
            color = color.replace("bright", "bright_")

        if not color:
            color = None

        string.append((value, {"color": color}))
    return string


def get_previous_lines(
    display_information: DisplayInformation,
    num: int = 2,
) -> FormattedString:
    if display_information.first_changed_line < 0:
        return ""
    lines = _remove_empty_lines(
        [
            display_information.file_lines[i]
            for i in range(
                max(0, display_information.first_changed_line - num),
                min(
                    display_information.first_changed_line,
                    len(display_information.file_lines),
                ),
            )
        ]
    )
    buffered = [" " * display_information.line_number_buffer + line for line in lines]

    prev = "\n".join(buffered)
    return highlight_text(prev, display_information.lexer)


def get_later_lines(
    display_information: DisplayInformation,
    num: int = 2,
) -> FormattedString:
    if display_information.last_changed_line < 0:
        return ""
    lines = _remove_empty_lines(
        [
            display_information.file_lines[i]
            for i in range(
                max(0, display_information.last_changed_line),
                min(
                    display_information.last_changed_line + num,
                    len(display_information.file_lines),
                ),
            )
        ]
    )
    buffered = [" " * (display_information.line_number_buffer) + line for line in lines]

    later = "\n".join(buffered)
    return highlight_text(later, display_information.lexer)
