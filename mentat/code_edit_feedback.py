from mentat.parsers.file_edit import FileEdit
from mentat.session_input import collect_user_input
from mentat.session_stream import SESSION_STREAM

from .code_context import CODE_CONTEXT
from .code_file_manager import CODE_FILE_MANAGER
from .conversation import CONVERSATION


async def get_user_feedback_on_edits(
    file_edits: list[FileEdit],
) -> bool:
    stream = SESSION_STREAM.get()
    conversation = CONVERSATION.get()
    code_file_manager = CODE_FILE_MANAGER.get()
    code_context = CODE_CONTEXT.get()

    await stream.send(
        "Apply these changes? 'Y/n/i' or provide feedback.",
        color="light_blue",
    )
    user_response_message = await collect_user_input()
    user_response = user_response_message.data

    need_user_request = True
    match user_response.lower():
        case "y" | "":
            edits_to_apply = file_edits
            conversation.add_user_message("User chose to apply all your changes.")
        case "n":
            edits_to_apply = []
            conversation.add_user_message(
                "User chose not to apply any of your changes."
            )
        case "i":
            edits_to_apply = await _user_filter_changes(file_edits)
            conversation.add_user_message(
                "User chose to apply"
                f" {len(edits_to_apply)}/{len(file_edits)} of your suggested"
                " changes."
            )
        case _:
            need_user_request = False
            edits_to_apply = []
            conversation.add_user_message(
                "User chose not to apply any of your changes. User response:"
                f" {user_response}\n\nPlease adjust your previous plan and changes to"
                " reflect this. Respond with a full new set of changes."
            )

    for file_edit in edits_to_apply:
        await file_edit.resolve_conflicts()

    if edits_to_apply:
        await code_file_manager.write_changes_to_files(edits_to_apply, code_context)
        await stream.send("Changes applied.", color="light_blue")
    else:
        await stream.send("No changes applied.", color="light_blue")

    if need_user_request:
        await stream.send("Can I do anything else for you?", color="light_blue")

    return need_user_request


async def _user_filter_changes(file_edits: list[FileEdit]) -> list[FileEdit]:
    new_edits = list[FileEdit]()
    for file_edit in file_edits:
        if await file_edit.filter_replacements():
            new_edits.append(file_edit)

    return new_edits
