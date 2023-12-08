from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class RedoCommand(Command, command_name="redo"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager

        errors = await code_file_manager.history.redo()
        if errors:
            stream.send(errors)
        stream.send("Redo complete", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Redo the last change made by Mentat"
