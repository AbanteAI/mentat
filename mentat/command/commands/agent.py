from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class AgentCommand(Command, command_name="agent"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        agent_handler = session_context.agent_handler

        if agent_handler.agent_enabled:
            agent_handler.disable_agent_mode()
            stream.send("Agent mode disabled", style="success")
        else:
            await agent_handler.enable_agent_mode()
            stream.send("Agent mode enabled", style="success")

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
        return (
            "Toggle agent mode. In agent mode Mentat will automatically make changes"
            " and run commands."
        )
