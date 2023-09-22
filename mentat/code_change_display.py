import math

from .code_change import CodeChange, CodeChangeAction
from .session_stream import get_session_stream

change_delimiter = 60 * "="


def _remove_extra_empty_lines(lines):
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


def _prefixed_lines(code_change, lines, prefix):
    return "\n".join(
        [
            prefix
            + " " * (code_change.line_number_buffer - len(prefix))
            + line.strip("\n")
            for line in lines
        ]
    )


async def print_change(code_change: CodeChange):
    stream = get_session_stream()

    await print_file_name(code_change)
    if code_change.action != CodeChangeAction.RenameFile:
        await stream.send(change_delimiter)
    await print_previous_lines(code_change)
    await print_removed_block(code_change)
    await print_added_block(code_change)
    await print_later_lines(code_change)
    if code_change.action != CodeChangeAction.RenameFile:
        await stream.send(change_delimiter)


async def print_file_name(code_change: CodeChange):
    stream = get_session_stream()

    file_name = code_change.file
    match code_change.action:
        case CodeChangeAction.CreateFile:
            await stream.send(f"{file_name}*", color="light_green")
        case CodeChangeAction.DeleteFile:
            await stream.send(f"{file_name}", color="light_red")
        case CodeChangeAction.RenameFile:
            await stream.send(
                f"Rename: {file_name} -> {code_change.name}", color="yellow"
            )
        case _:
            await stream.send(f"{file_name}", color="light_blue")


async def print_removed_block(code_change, prefix="-", color="red"):
    if code_change.action.has_removals():
        if code_change.action == CodeChangeAction.DeleteFile:
            changed_lines = code_change.file_lines
        else:
            changed_lines = code_change.file_lines[
                code_change.first_changed_line - 1 : code_change.last_changed_line
            ]

        removed = _prefixed_lines(code_change, changed_lines, prefix)
        if removed:
            stream = get_session_stream()
            await stream.send(removed, color=color)


async def print_added_block(code_change, prefix="+", color: str | None = "green"):
    if code_change.action.has_additions():
        added = _prefixed_lines(code_change, code_change.code_lines, prefix)
        if added:
            stream = get_session_stream()
            await stream.send(added, color=color)


async def print_previous_lines(code_change: CodeChange, num: int = 2):
    if not code_change.action.has_surrounding_lines():
        return

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
        stream = get_session_stream()
        await stream.send(prev, file_name_for_lexer=code_change.file)


async def print_later_lines(code_change: CodeChange, num: int = 2):
    if not code_change.action.has_surrounding_lines():
        return
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
        stream = get_session_stream()
        await stream.send(later, file_name_for_lexer=code_change.file)
