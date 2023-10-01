from enum import Enum
from pathlib import Path

import attr
from pygments.lexer import Lexer
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

from mentat.session_stream import get_session_stream

change_delimiter = 60 * "="


def _get_lexer(file_path: Path):
    try:
        lexer: Lexer = get_lexer_for_filename(file_path)
    except ClassNotFound:
        lexer = TextLexer()
    lexer.stripnl = False
    lexer.stripall = False
    lexer.ensurenl = False
    return lexer


def get_line_number_buffer(file_lines: list[str]):
    return len(str(len(file_lines) + 1)) + 1


class FileActionType(Enum):
    RenameFile = "rename"
    CreateFile = "create"
    DeleteFile = "delete"
    UpdateFile = "update"


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
        self.line_number_buffer = get_line_number_buffer(self.file_lines)
        self.lexer = _get_lexer(self.file_name)


def _remove_extra_empty_lines(lines: list[str]) -> list[str]:
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

    # If all lines are empty, keep only one empty line
    if start == len(lines):
        return [" "]

    # Return the list with only a maximum of one empty line on either side
    return lines[max(start - 1, 0) : end + 2]


def _prefixed_lines(line_number_buffer: int, lines: list[str], prefix: str):
    return "\n".join(
        [
            prefix + " " * (line_number_buffer - len(prefix)) + line.strip("\n")
            for line in lines
        ]
    )


async def _print_code_block(
    code_lines: list[str],
    line_number_buffer: int,
    prefix: str,
    color: str | None,
):
    stream = get_session_stream()
    lines = _prefixed_lines(line_number_buffer, code_lines, prefix)
    if lines:
        await stream.send(lines, color=color)


async def print_full_change(display_information: DisplayInformation):
    stream = get_session_stream()

    await print_file_name(display_information)
    if display_information.added_block or display_information.removed_block:
        await stream.send(change_delimiter)
    await print_previous_lines(display_information)
    await print_removed_lines(display_information)
    await print_added_lines(display_information)
    await print_later_lines(display_information)
    if display_information.added_block or display_information.removed_block:
        await stream.send(change_delimiter)


async def print_file_name(display_information: DisplayInformation):
    stream = get_session_stream()
    match display_information.file_action_type:
        case FileActionType.CreateFile:
            await stream.send(
                f"\n{display_information.file_name}*", color="light_green"
            )
        case FileActionType.DeleteFile:
            await stream.send(
                f"\nDeletion: {display_information.file_name}", color="light_red"
            )
        case FileActionType.RenameFile:
            await stream.send(
                f"\nRename: {display_information.file_name} ->"
                f" {display_information.new_name}",
                color="yellow",
            )
        case FileActionType.UpdateFile:
            await stream.send(f"\n{display_information.file_name}", color="light_blue")


async def print_added_lines(
    display_information: DisplayInformation,
    prefix: str = "+",
    color: str | None = "green",
):
    await _print_code_block(
        display_information.added_block,
        display_information.line_number_buffer,
        prefix,
        color,
    )


async def print_removed_lines(
    display_information: DisplayInformation,
    prefix: str = "-",
    color: str | None = "red",
):
    await _print_code_block(
        display_information.removed_block,
        display_information.line_number_buffer,
        prefix,
        color,
    )


async def print_previous_lines(display_information: DisplayInformation, num: int = 2):
    stream = get_session_stream()

    if display_information.first_changed_line < 0:
        return
    lines = _remove_extra_empty_lines(
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
    numbered = [
        (str(display_information.first_changed_line - len(lines) + i + 1) + ":").ljust(
            display_information.line_number_buffer
        )
        + line
        for i, line in enumerate(lines)
    ]

    prev = "\n".join(numbered)

    await stream.send(prev, lexer=display_information.lexer, bg="dark")


async def print_later_lines(display_information: DisplayInformation, num: int = 2):
    stream = get_session_stream()

    if display_information.last_changed_line < 0:
        return
    lines = _remove_extra_empty_lines(
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
    numbered = [
        (str(display_information.last_changed_line + 1 + i) + ":").ljust(
            display_information.line_number_buffer
        )
        + line
        for i, line in enumerate(lines)
    ]

    later = "\n".join(numbered)

    await stream.send(later, lexer=display_information.lexer, bg="dark")
