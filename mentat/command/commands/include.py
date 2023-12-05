from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path


class IncludeCommand(Command, command_name="include"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        if len(args) == 0:
            stream.send("No files specified", color="yellow")
            return
        for file_path in args:
            included_paths = code_context.include(file_path)
            for included_path in included_paths:
                rel_path = get_relative_path(included_path, session_context.cwd)
                stream.send(f"{rel_path} added to context", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Add files to the code context"
