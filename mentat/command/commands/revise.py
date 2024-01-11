from typing import List

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import ModelMessage


class ReviseCommand(Command, command_name="revise"):
    @override
    async def apply(self, *args: str) -> None:
        ctx = SESSION_CONTEXT.get()

        prompt = ctx.config.parser.get_system_prompt()
        prompt_message = ChatCompletionSystemMessageParam(
            role="system",
            content=prompt,
        )
        request_message = ChatCompletionUserMessageParam(
            role="user",
            content=(
                "Your job is to fix any syntax errors there may be in the file you are"
                " given."
            ),
        )
        file = (ctx.cwd / args[0]).resolve()
        file_message = ChatCompletionSystemMessageParam(
            role="system",
            content=f"Code Files:\n{args[0]}\n"
            + "\n".join(ctx.code_file_manager.file_lines[file]),
        )
        messages: List[ChatCompletionMessageParam] = [
            prompt_message,
            request_message,
            file_message,
        ]
        response = await ctx.llm_api_handler.call_llm_api(
            messages, model=ctx.config.model, stream=False
        )
        message = response.choices[0].message.content or ""
        messages.append(
            ChatCompletionAssistantMessageParam(content=message, role="assistant")
        )
        ctx.conversation.add_transcript_message(
            ModelMessage(
                message=message, prior_messages=messages, message_type="revisor"
            )
        )

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("required", "file")]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return get_command_filename_completions(arguments[-1])

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Revise a file to remove any syntax errors."
