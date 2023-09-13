import math

from pygments import highlight  # pyright: ignore[reportUnknownVariableType]
from pygments.formatters import TerminalFormatter
from termcolor import colored

from .code_change import CodeChange, CodeChangeAction

change_delimiter = 60 * "="


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


def _prefixed_lines(code_change: CodeChange, lines: list[str], prefix: str):
    return "\n".join(
        [
            prefix
            + " " * (code_change.line_number_buffer - len(prefix))
            + line.strip("\n")
            for line in lines
        ]
    )


def print_change(code_change: CodeChange):
    to_print = [
        get_file_name(code_change),
        change_delimiter if code_change.action != CodeChangeAction.RenameFile else "",
        get_previous_lines(code_change),
        get_removed_block(code_change),
        get_added_block(code_change),
        get_later_lines(code_change),
        change_delimiter if code_change.action != CodeChangeAction.RenameFile else "",
    ]
    for s in to_print:
        if s:
            print(s)


def get_file_name(code_change: CodeChange):
    file_name = code_change.file
    match code_change.action:
        case CodeChangeAction.CreateFile:
            return colored(f"\n{file_name}*", color="light_green")
        case CodeChangeAction.DeleteFile:
            return colored(f"\n{file_name}", color="light_red")
        case CodeChangeAction.RenameFile:
            return colored(
                f"\nRename: {file_name} -> {code_change.name}", color="yellow"
            )
        case _:
            return colored(f"\n{file_name}", color="light_blue")


def get_removed_block(
    code_change: CodeChange, prefix: str = "-", color: str | None = "red"
):
    if code_change.action.has_removals():
        if code_change.action == CodeChangeAction.DeleteFile:
            changed_lines = code_change.file_lines
        else:
            changed_lines = code_change.file_lines[
                code_change.first_changed_line - 1 : code_change.last_changed_line
            ]

        removed = _prefixed_lines(code_change, changed_lines, prefix)
        if removed:
            return colored(removed, color=color)
    return ""


def get_added_block(
    code_change: CodeChange, prefix: str = "+", color: str | None = "green"
):
    if code_change.action.has_additions():
        added = _prefixed_lines(code_change, code_change.code_lines, prefix)
        if added:
            return colored(added, color=color)
    return ""


def get_previous_lines(code_change: CodeChange, num: int = 2):
    if not code_change.action.has_surrounding_lines():
        return ""
    lines = _remove_extra_empty_lines(
        [
            code_change.file_lines[i]
            for i in range(
                max(0, math.ceil(code_change.first_changed_line) - (num + 1)),
                min(
                    math.ceil(code_change.first_changed_line) - 1,
                    len(code_change.file_lines),
                ),
            )
        ]
    )
    numbered = [
        (str(math.ceil(code_change.first_changed_line) - len(lines) + i) + ":").ljust(
            code_change.line_number_buffer
        )
        + line
        for i, line in enumerate(lines)
    ]

    prev = "\n".join(numbered)
    if prev:
        # pygments doesn't have type hints on TerminalFormatter
        h_prev: str = highlight(prev, code_change.lexer, TerminalFormatter(bg="dark"))  # type: ignore
        return h_prev
    return ""


def get_later_lines(code_change: CodeChange, num: int = 2):
    if not code_change.action.has_surrounding_lines():
        return ""
    lines = _remove_extra_empty_lines(
        [
            code_change.file_lines[i]
            for i in range(
                max(0, int(code_change.last_changed_line)),
                min(
                    int(code_change.last_changed_line) + num,
                    len(code_change.file_lines),
                ),
            )
        ]
    )
    numbered = [
        (str(int(code_change.last_changed_line) + 1 + i) + ":").ljust(
            code_change.line_number_buffer
        )
        + line
        for i, line in enumerate(lines)
    ]

    later = "\n".join(numbered)
    if later:
        # pygments doesn't have type hints on TerminalFormatter
        h_later: str = highlight(later, code_change.lexer, TerminalFormatter(bg="dark"))  # type: ignore
        return h_later
    return ""
