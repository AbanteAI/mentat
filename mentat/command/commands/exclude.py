from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path


class ExcludeCommand(Command, command_name="exclude"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        if len(args) == 0:
            stream.send("No files specified", color="yellow")
            return
        for file_path in args:
            excluded_paths = code_context.exclude(file_path)
            for excluded_path in excluded_paths:
                rel_path = get_relative_path(excluded_path, session_context.cwd)
                stream.send(f"{rel_path} removed from context", color="red")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Remove files from the code context"
