from pathlib import Path

from mentat.command.command import Command
from mentat.include_files import print_invalid_path
from mentat.session_context import SESSION_CONTEXT


class IncludeCommand(Command, command_name="include"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        if len(args) == 0:
            stream.send("No files specified", color="yellow")
            return
        for file_path in args:
            included_paths, invalid_paths = code_context.include_file(
                Path(file_path).absolute()
            )
            for invalid_path in invalid_paths:
                print_invalid_path(invalid_path)
            for included_path in included_paths:
                if included_path.is_relative_to(session_context.cwd):
                    display_path = included_path.relative_to(session_context.cwd)
                else:
                    display_path = included_path
                stream.send(f"{display_path} added to context", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Add files to the code context"
