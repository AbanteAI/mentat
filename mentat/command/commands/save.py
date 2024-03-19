import json
from pathlib import Path
from typing import List

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.errors import PathValidationError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path


class SaveCommand(Command, command_name="save"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        context_file_path = mentat_dir_path / "context.json"

        if len(args) > 1:
            stream.send("Only one context file can be saved at a time", style="warning")
            return

        if len(args) == 1:
            try:
                context_file_path = Path(args[0]).expanduser().resolve()
            except RuntimeError as e:
                raise PathValidationError(f"Invalid context file path provided: {args[0]}: {e}")

        serializable_context = code_context.to_simple_context_dict()

        with open(context_file_path, "w") as file:
            json.dump(serializable_context, file)

        stream.send(f"Context saved to {context_file_path}", style="success")

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("optional", ["path"])]

    @override
    @classmethod
    def argument_autocompletions(cls, arguments: list[str], argument_position: int) -> list[str]:
        return get_command_filename_completions(arguments[-1])

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Saves the current context to a file."
