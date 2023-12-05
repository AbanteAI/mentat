from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class ClearCommand(Command, command_name="clear"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        conversation = session_context.conversation

        conversation.clear_messages()
        message = "Message history cleared"
        stream.send(message, color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Clear the current conversation's message history"
