from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class ContextCommand(Command, command_name="context"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        code_context = session_context.code_context

        code_context.display_context()

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return []

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Show all files currently in context."
