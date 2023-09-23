from typing import Iterable

from .code_change import CodeChange, CodeChangeAction
from .code_change_display import print_change
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager
from .llm_conversation import LLMConversation
from .session_input import ask_yes_no, collect_user_input
from .session_stream import get_session_stream


async def user_filter_changes(
    code_changes: Iterable[CodeChange],
) -> Iterable[CodeChange]:
    stream = get_session_stream()

    new_changes = []
    indices = []
    for index, change in enumerate(code_changes, start=1):
        await print_change(change)
        # Allowing the user to remove rename file changes introduces a lot of edge cases
        if change.action == CodeChangeAction.RenameFile:
            new_changes.append(change)
            indices.append(index)
            await stream.send("Cannot remove rename file change", color="light_yellow")
            continue

        await stream.send("Keep this change?", color="light_blue")
        should_keep_change = await ask_yes_no(default_yes=True)
        if should_keep_change:
            new_changes.append(change)
            indices.append(index)

    return new_changes, indices


async def get_user_feedback_on_changes(
    config: ConfigManager,
    conv: LLMConversation,
    code_file_manager: CodeFileManager,
    code_changes: Iterable[CodeChange],
) -> bool:
    stream = get_session_stream()

    await stream.send(
        "Apply these changes? 'Y/n/i' or provide feedback.", color="light_blue"
    )
    user_response = await collect_user_input()

    need_user_request = True
    match user_response.data.lower():
        case "y" | "":
            code_changes_to_apply = code_changes
            conv.add_user_message("User chose to apply all your changes.")
        case "n":
            code_changes_to_apply = []
            conv.add_user_message("User chose not to apply any of your changes.")
        case "i":
            code_changes_to_apply, indices = await user_filter_changes(code_changes)
            conv.add_user_message(
                "User chose to apply"
                f" {len(code_changes_to_apply)}/{len(code_changes)} of your suggest"
                " changes. The changes they applied were:"
                f" {', '.join(map(str, indices))}"
            )
        case _:
            need_user_request = False
            code_changes_to_apply = []
            conv.add_user_message(
                "User chose not to apply any of your changes. User response:"
                f" {user_response}\n\nPlease adjust your previous plan and changes to"
                " reflect this. Respond with a full new set of changes."
            )

    if code_changes_to_apply:
        await code_file_manager.write_changes_to_files(code_changes_to_apply)
        if len(code_changes_to_apply) == len(code_changes):
            await stream.send("Changes applied.", color="light_blue")
        else:
            await stream.send("Selected changes applied.", color="light_blue")
    else:
        await stream.send("No changes applied.", color="light_blue")

    if need_user_request:
        await stream.send("Can I do anything else for you?", color="light_blue")

    return need_user_request
