import difflib
from pathlib import Path
from typing import List

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from mentat.errors import MentatError
from mentat.llm_api_handler import prompt_tokens
from mentat.parsers.change_display_helper import get_lexer, highlight_text
from mentat.parsers.file_edit import FileEdit
from mentat.parsers.git_parser import GitParser
from mentat.parsers.streaming_printer import FormattedString, send_formatted_string
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import ModelMessage
from mentat.utils import get_relative_path

revisor_prompt_filename = Path("revisor_prompt.txt")
revisor_prompt = read_prompt(revisor_prompt_filename)


def _get_stored_lines(file_edit: FileEdit) -> List[str]:
    ctx = SESSION_CONTEXT.get()

    if file_edit.is_creation:
        return []
    else:
        return ctx.code_file_manager.file_lines[file_edit.file_path].copy()


def _file_edit_diff(file_edit: FileEdit) -> str:
    stored_lines = _get_stored_lines(file_edit)
    new_lines = file_edit.get_updated_file_lines(stored_lines)
    diff = list(difflib.unified_diff(stored_lines, new_lines, lineterm=""))
    return "\n".join(diff)


async def revise_edit(file_edit: FileEdit):
    ctx = SESSION_CONTEXT.get()

    # No point in revising deletion edits
    if file_edit.is_deletion:
        return
    diff = _file_edit_diff(file_edit)
    # There should always be a user_message by the time we're revising
    user_message = list(
        filter(
            lambda message: message["role"] == "user",
            await ctx.conversation.get_messages(),
        )
    )[-1]
    user_message["content"] = f"User Request:\n{user_message.get('content')}"
    messages: List[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(content=revisor_prompt, role="system"),
        user_message,
        ChatCompletionSystemMessageParam(content=f"Diff:\n{diff}", role="system"),
    ]
    code_message = await ctx.code_context.get_code_message(prompt_tokens(messages, ctx.config.model))
    messages.insert(1, ChatCompletionSystemMessageParam(content=code_message, role="system"))

    ctx.stream.send(
        "\nRevising edits for file" f" {get_relative_path(file_edit.file_path, ctx.cwd)}...",
        style="info",
    )
    response = await ctx.llm_api_handler.call_llm_api(messages, model=ctx.config.model, stream=False)
    message = response.text
    messages.append(ChatCompletionAssistantMessageParam(content=message, role="assistant"))
    ctx.conversation.add_transcript_message(
        ModelMessage(message=message, prior_messages=messages, message_type="revisor")
    )

    # Sometimes the model wraps response in a ```diff ``` block
    # I believe new prompt fixes this but this makes sure it never interferes
    if message.startswith("```diff\n"):
        message = message[8:]
        if message.endswith("\n```"):
            message = message[:-4]

    # This makes it more similar to a git diff so that we can use the pre existing git diff parser
    message = "\n".join(message.split("\n")[2:])  # remove leading +++ and ---
    post_diff = "diff --git a/file b/file\nindex 0000000..0000000\n--- a/file\n+++" f" b/file\n{message}"
    parsed_response = GitParser().parse_llm_response(post_diff)

    # Only modify the replacements of the current file edit
    # (the new file edit doesn't know about file creation or renaming)
    # Additionally, since we do this one at a time there should only ever be 1 file edit.
    if parsed_response.file_edits:
        stored_lines = _get_stored_lines(file_edit)
        pre_lines = file_edit.get_updated_file_lines(stored_lines)
        file_edit.replacements = parsed_response.file_edits[0].replacements
        post_lines = file_edit.get_updated_file_lines(stored_lines)

        diff_lines = difflib.unified_diff(pre_lines, post_lines, lineterm="")
        diff_diff: List[FormattedString] = []
        lexer = get_lexer(file_edit.file_path)
        for line in diff_lines:
            if line.startswith("---"):
                diff_diff.append(f"{line}{file_edit.file_path}")
            elif line.startswith("+++"):
                new_name = file_edit.rename_file_path if file_edit.rename_file_path is not None else file_edit.file_path
                diff_diff.append(f"{line}{new_name}")
            elif line.startswith("@@"):
                diff_diff.append(line)
            elif line.startswith("+"):
                diff_diff.append((line, {"color": "green"}))
            elif line.startswith("-"):
                diff_diff.append((line, {"color": "red"}))
            elif line.startswith(" "):
                diff_diff.append(highlight_text(line, lexer))
            else:
                raise MentatError("Invalid Diff")
        if diff_diff:
            ctx.stream.send("Revision diff:", style="info")
            ctx.stream.send("", delimiter=True)
            for line in diff_diff:
                send_formatted_string(line)
            ctx.stream.send("", delimiter=True)
        ctx.cost_tracker.display_last_api_call()


async def revise_edits(file_edits: List[FileEdit]):
    for file_edit in file_edits:
        # We could do all edits asynchronously; of course, this risks getting rate limited and probably not worth effort
        await revise_edit(file_edit)
