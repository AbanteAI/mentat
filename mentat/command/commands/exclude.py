from pathlib import Path

from mentat.command.command import Command
from mentat.include_files import print_invalid_path
from mentat.session_context import SESSION_CONTEXT


class ExcludeCommand(Command, command_name="exclude"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        if len(args) == 0:
            stream.send("No files specified", color="yellow")
            return
        for file_path in args:
            excluded_paths, invalid_paths = code_context.exclude_file(
                Path(file_path).absolute()
            )
            for invalid_path in invalid_paths:
                print_invalid_path(invalid_path)
            for excluded_path in excluded_paths:
                if excluded_path.is_relative_to(session_context.cwd):
                    display_path = excluded_path.relative_to(session_context.cwd)
                else:
                    display_path = excluded_path
                stream.send(f"{display_path} removed from context", color="red")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Remove files from the code context"
