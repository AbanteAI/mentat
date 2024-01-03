from typing import List

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class RunCommand(Command, command_name="run"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        conversation = session_context.conversation
        if not args:
            stream.send("No command given", style="failure")
            return
        await conversation.run_command(list(args))

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [
            CommandArgument("required", "command"),
            CommandArgument("optional", "args", repeatable=True),
        ]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return get_command_filename_completions(arguments[-1])

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Run a shell command and put its output in context."
