from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class AmendCommand(Command, command_name="amend"):
    @override
    async def apply(self, *args: str) -> None:
        ctx = SESSION_CONTEXT.get()

        last_message = ctx.conversation.amend()
        if last_message:
            ctx.stream.send("Previous response removed from context.", style="info")
            ctx.stream.send(last_message, channel="default_prompt")
        else:
            ctx.stream.send("No previous user requests to amend.", style="warning")

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
        return (
            "Used to amend a previous user request. Works by resetting context to the"
            " state it was at the last request and prefills user input with the last"
            " request. Does not undo any edits."
        )
