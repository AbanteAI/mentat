from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class RunCommand(Command, command_name="run"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        conversation = session_context.conversation
        if not args:
            stream.send("No command given", color="dark_red")
            return
        await conversation.run_command(list(args))

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["command", "args..."]

    @classmethod
    def help_message(cls) -> str:
        return "Run a shell command and put its output in context."
