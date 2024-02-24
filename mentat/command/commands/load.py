from pathlib import Path
from typing import List
import json

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT
from mentat.errors import PathValidationError


class LoadCommand(Command, command_name="load"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        if len(args) == 0:
            stream.send("No context file specified", style="warning")
            return

        if len(args) > 1:
            stream.send(
                "Only one context file can be loaded at a time", style="warning"
            )
            return

        try:
            context_file = Path(args[0]).expanduser().resolve()
        except RuntimeError as e:
            raise PathValidationError(
                f"Invalid context file path provided: {args[0]}: {e}"
            )

        with open(context_file, "r") as file:
            parsed_include_files = json.load(file)

        # TODO: Do we remove already included files when loading new context file?
        code_context.include_files = parsed_include_files

        stream.send(f"Context loaded from {context_file}", style="success")

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("required", ["path"])]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return get_command_filename_completions(arguments[-1])

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Loads a context file."
