from pathlib import Path
from typing import List

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path


class ExcludeCommand(Command, command_name="exclude"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        if len(args) == 0:
            stream.send("No files specified", style="warning")
            return
        for file_path in args:
            excluded_paths = code_context.exclude(file_path)
            for excluded_path in excluded_paths:
                rel_path = get_relative_path(excluded_path, session_context.cwd)
                stream.send(f"{rel_path} removed from context", style="error")

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("required", ["path", "glob pattern"], repeatable=True)]

    @override
    @classmethod
    def argument_autocompletions(cls, arguments: list[str], argument_position: int) -> list[str]:
        ctx = SESSION_CONTEXT.get()

        file_names = get_command_filename_completions(arguments[-1])
        filtered_file_names: List[str] = []
        for file_name in file_names:
            file_path = Path(file_name).expanduser().resolve()
            for included_file in ctx.code_context.include_files.keys():
                if included_file.is_relative_to(file_path):
                    filtered_file_names.append(file_name)
                    break

        return filtered_file_names

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Remove files from context."
