from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class ContextCommand(Command, command_name="context"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        code_context = session_context.code_context

        code_context.display_context()

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Shows all files currently in Mentat's context"
