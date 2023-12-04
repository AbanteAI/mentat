from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class UndoCommand(Command, command_name="undo"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager

        errors = code_file_manager.history.undo()
        if errors:
            stream.send(errors)
        stream.send("Undo complete", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Undo the last change made by Mentat"
