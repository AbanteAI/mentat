from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class UndoAllCommand(Command, command_name="undo-all"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager

        errors = code_file_manager.history.undo_all()
        if errors:
            stream.send("\n".join(errors), style="error")
        stream.send("Undos complete", style="success")

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return []

    @override
    @classmethod
    def argument_autocompletions(cls, arguments: list[str], argument_position: int) -> list[str]:
        return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Undo all changes made by Mentat."
