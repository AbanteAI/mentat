from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT

help_message_width = 60


def _arg_message(arg: CommandArgument) -> str:
    if isinstance(arg.description, str):
        cur_message = arg.description
    else:
        cur_message = "|".join(arg.description)

    match arg.arg_type:
        case "required":
            cur_message = "<" + cur_message + ">"
        case "optional":
            cur_message = "[" + cur_message + "]"
        case "literal":
            pass

    if arg.repeatable:
        cur_message += " ..."

    return cur_message


class HelpCommand(Command, command_name="help"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        if not args:
            commands = Command.get_command_names()
        else:
            commands = args
        for command_name in commands:
            if command_name not in Command._registered_commands:
                stream.send(
                    f"Error: Command {command_name} does not exist.", style="error"
                )
            else:
                command_cls = Command._registered_commands[command_name]
                arguments = command_cls.arguments()
                argument_message = [_arg_message(arg) for arg in arguments]

                help_message = command_cls.help_message()
                message = (
                    " ".join([f"/{command_name}"] + argument_message).ljust(
                        help_message_width
                    )
                    + help_message
                )
                stream.send(message)

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("optional", "command", repeatable=True)]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return Command.get_command_names()

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Show information on available commands."
