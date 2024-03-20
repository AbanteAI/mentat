from openai.types.chat import ChatCompletionSystemMessageParam

from mentat.parsers.file_edit import FileEdit
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import collect_user_input


async def get_user_feedback_on_edits(
    file_edits: list[FileEdit],
) -> tuple[list[FileEdit], bool]:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    conversation = session_context.conversation

    stream.send(
        "Apply these changes? 'Y/n/i' or provide feedback.",
        style="input",
    )
    user_response_message = await collect_user_input()
    user_response = user_response_message.data

    need_user_request = True
    match user_response.lower():
        case "y" | "":
            edits_to_apply = file_edits
            conversation.add_message(
                ChatCompletionSystemMessageParam(role="system", content="User chose to apply all your changes.")
            )
        case "n":
            edits_to_apply = []
            conversation.add_message(
                ChatCompletionSystemMessageParam(
                    role="system",
                    content="User chose not to apply any of your changes.",
                )
            )
        case "i":
            edits_to_apply = await _user_filter_changes(file_edits)
            if len(edits_to_apply) > 0:
                conversation.add_message(
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="User chose to apply some of your changes.",
                    )
                )
            else:
                conversation.add_message(
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="User chose not to apply any of your changes.",
                    )
                )

        case _:
            need_user_request = False
            edits_to_apply = []
            conversation.add_message(
                ChatCompletionSystemMessageParam(
                    role="system",
                    content="User chose not to apply any of your changes.",
                )
            )
            conversation.add_user_message(user_response)
    return edits_to_apply, need_user_request


async def _user_filter_changes(file_edits: list[FileEdit]) -> list[FileEdit]:
    new_edits = list[FileEdit]()
    for file_edit in file_edits:
        if await file_edit.filter_replacements():
            new_edits.append(file_edit)

    return new_edits
