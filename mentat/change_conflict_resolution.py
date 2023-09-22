import logging
import string

from .code_change import CodeChange, CodeChangeAction
from .code_change_display import get_added_block, get_removed_block
from .session_input import ask_yes_no, collect_user_input
from .session_stream import get_session_stream


async def resolve_insertion_conflicts(
    changes: list[CodeChange],
    code_file_manager,
) -> list[CodeChange]:
    """merges insertion conflicts into one singular code change"""
    stream = get_session_stream()

    insert_changes = list(
        filter(
            lambda change: change.action == CodeChangeAction.Insert,
            sorted(changes, reverse=True),
        )
    )
    new_insert_changes = []
    cur = 0
    while cur < len(insert_changes):
        end = cur + 1
        while (
            end < len(insert_changes)
            and insert_changes[end].first_changed_line
            == insert_changes[cur].first_changed_line
        ):
            end += 1
        if end > cur + 1:
            logging.debug("insertion conflict")
            await stream.send("Insertion conflict:", color="red")
            for i in range(end - cur):
                await stream.send(f"({string.printable[i]})", color="green")
                await stream.send(
                    "\n".join(insert_changes[cur + i].code_lines), color="light_cyan"
                )
            await stream.send(
                "Type the order in which to insert changes (omit for no preference):"
            )
            user_input = await collect_user_input()
            new_code_lines = []
            used = set()
            for c in user_input.data:
                index = string.printable.index(c) if c in string.printable else -1
                if index < end - cur and index != -1:
                    new_code_lines += insert_changes[cur + index].code_lines
                    used.add(index)
            for i in range(end - cur):
                if i not in used:
                    new_code_lines += insert_changes[cur + i].code_lines
            new_change = CodeChange(
                insert_changes[cur].json_data,
                new_code_lines,
                code_file_manager,
            )
            new_insert_changes.append(new_change)
        else:
            new_insert_changes.append(insert_changes[cur])
        cur = end
    return sorted(
        list(filter(lambda change: change.action != CodeChangeAction.Insert, changes))
        + new_insert_changes,
        reverse=True,
    )


async def resolve_non_insertion_conflicts(
    changes: list[CodeChange],
) -> list[CodeChange]:
    """resolves delete-replace conflicts and asks user on delete-insert or replace-insert conflicts"""
    stream = get_session_stream()

    min_changed_line = changes[0].last_changed_line + 1
    removed_changes = set()
    for i, change in enumerate(changes):
        if change.last_changed_line >= min_changed_line:
            if change.action == CodeChangeAction.Insert:
                logging.debug("insertion inside removed block")
                if changes[i - 1].action == CodeChangeAction.Delete:
                    keep = True
                else:
                    await stream.send(
                        "Insertion conflict: Lines inserted inside replaced block",
                        color="light_red",
                    )
                    await stream.send(get_removed_block(changes[i - 1]))
                    await stream.send(get_added_block(change, prefix=">", color=None))
                    await stream.send(get_added_block(changes[i - 1]))
                    await stream.send("Keep this insertion?")
                    keep = await ask_yes_no(default_yes=True)
                if keep:
                    change.first_changed_line = changes[i - 1].first_changed_line - 0.5
                    change.last_changed_line = change.first_changed_line
                else:
                    removed_changes.add(i)

            else:
                change.last_changed_line = min_changed_line - 1
                change.first_changed_line = min(
                    change.first_changed_line, changes[i - 1].first_changed_line
                )
        min_changed_line = change.first_changed_line
    return [change for i, change in enumerate(changes) if i not in removed_changes]
