from pathlib import Path
from typing import List, Set

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)
from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.git_handler import get_git_diff
from mentat.include_files import get_code_features_for_path
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import ModelMessage
from mentat.utils import get_relative_path

test_selection_prompt_path = Path("test_selection_prompt.txt")
test_selection_prompt = read_prompt(test_selection_prompt_path)
test_selection_prompt_2_path = Path("test_selection_prompt_2.txt")
test_selection_prompt_2 = read_prompt(test_selection_prompt_2_path)


class TestCommand(Command, command_name="test"):
    @override
    async def apply(self, *args: str) -> None:
        ctx = SESSION_CONTEXT.get()

        target = args[0] if args else "main"
        diff = get_git_diff(target)

        features = ctx.code_context.get_all_features(split_intervals=False)
        messages: List[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system", content=test_selection_prompt
            ),
            ChatCompletionSystemMessageParam(
                role="system",
                content="\n".join(
                    str(feature.path.relative_to(ctx.cwd)) for feature in features
                ),
            ),
            ChatCompletionSystemMessageParam(role="system", content=diff),
        ]
        response = await ctx.llm_api_handler.call_llm_api(
            messages, model=ctx.config.model, stream=False
        )
        message = response.choices[0].message.content or ""
        messages.append(
            ChatCompletionAssistantMessageParam(content=message, role="assistant")
        )

        if message.strip() != "NO FILES NEEDED":
            included: Set[Path] = set()
            for line in message.split("\n"):
                included.update(ctx.code_context.include(line))
            for included_path in included:
                rel_path = get_relative_path(included_path, ctx.cwd)
                ctx.stream.send(f"{rel_path} added to context", style="success")

        messages.append(
            ChatCompletionSystemMessageParam(
                role="system", content=test_selection_prompt_2
            )
        )
        response = await ctx.llm_api_handler.call_llm_api(
            messages, model=ctx.config.model, stream=False
        )
        message = response.choices[0].message.content or ""
        messages.append(
            ChatCompletionAssistantMessageParam(content=message, role="assistant")
        )
        ctx.conversation.add_transcript_message(
            ModelMessage(message=message, prior_messages=messages, message_type="test")
        )

        all_tests: List[str] = []
        if message.strip() != "NO TESTS FOUND":
            for line in message.split("\n"):
                all_tests += [
                    feature.rel_path(ctx.cwd)
                    for feature in get_code_features_for_path(Path(line), ctx.cwd)
                ]

        ctx.conversation.add_user_message(
            "You will be given both a list of all existing test files in this"
            " repository as well as a git diff of a recent PR. Create a set of"
            " comprehensive tests for this PR if they don't already exist. Keep your"
            " changes laser focused! Only make tests for larger, broader additions or"
            " changes."
        )
        ctx.conversation.add_message(
            ChatCompletionSystemMessageParam(
                role="system", content="All test files:\n" + "\n".join(all_tests)
            )
        )
        ctx.conversation.add_message(
            ChatCompletionSystemMessageParam(role="system", content=diff)
        )
        parsed_llm_response = await ctx.conversation.get_model_response()
        file_edits = parsed_llm_response.file_edits
        await ctx.code_file_manager.write_changes_to_files(file_edits)

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("optional", "git tree-ish")]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return (
            "Write tests for a PR using the diff to the given branch or commit."
            " Defaults to main."
        )
