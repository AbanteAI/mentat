from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class AgentCommand(Command, command_name="agent"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        agent_handler = session_context.agent_handler

        if agent_handler.agent_enabled:
            agent_handler.disable_agent_mode()
            stream.send("Agent mode disabled", color="green")
        else:
            await agent_handler.enable_agent_mode()
            stream.send("Agent mode enabled", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return (
            "Toggle agent mode. In agent mode Mentat will automatically make changes,"
            " run pre-specified commands to test those changes, and"
            " adjust its changes."
        )
