from pathlib import Path
from typing import List

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path

import json


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

        # Load the context file
        context_file = Path(args[0]).expanduser().resolve()

        # Parse the context file
        with open(context_file, "r") as file:
            parsed_new_context = json.load(file)  # should be array of strings

        for file_path in parsed_new_context:
            included_paths = code_context.include(file_path)
            for included_path in included_paths:
                rel_path = get_relative_path(included_path, session_context.cwd)
                stream.send(f"{rel_path} added to context", style="success")

        # TODO: Ask if we remove included files when loading new context file

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
