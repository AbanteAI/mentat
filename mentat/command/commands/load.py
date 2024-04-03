import json
from pathlib import Path
from typing import List

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.errors import PathValidationError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path


class LoadCommand(Command, command_name="load"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        context_file_path = mentat_dir_path / "context.json"

        if len(args) > 1:
            stream.send("Only one context file can be loaded at a time", style="warning")
            return

        if args:
            path_arg = args[0]
            try:
                context_file_path = Path(path_arg).expanduser().resolve()
            except RuntimeError as e:
                raise PathValidationError(f"Invalid context file path provided: {path_arg}: {e}")

        try:
            with open(context_file_path, "r") as file:
                parsed_include_files = json.load(file)
        except FileNotFoundError:
            stream.send(f"Context file not found at {context_file_path}", style="error")
            return
        except json.JSONDecodeError as e:
            stream.send(
                f"Failed to parse context file at {context_file_path}: {e}",
                style="error",
            )
            return

        code_context.from_simple_context_dict(parsed_include_files)

        stream.send(f"Context loaded from {context_file_path}", style="success")

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
        return "Loads a context file. Loaded context adds to existing context, it does not replace it."
