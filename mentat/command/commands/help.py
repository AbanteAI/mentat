from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT

help_message_width = 60


class HelpCommand(Command, command_name="help"):
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
                    f"Error: Command {command_name} does not exist.", color="red"
                )
            else:
                command_class = Command._registered_commands[command_name]
                argument_names = command_class.argument_names()
                help_message = command_class.help_message()
                message = (
                    " ".join(
                        [f"/{command_name}"] + [f"<{arg}>" for arg in argument_names]
                    ).ljust(help_message_width)
                    + help_message
                )
                stream.send(message)

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["command"]

    @classmethod
    def help_message(cls) -> str:
        return "Displays this message"
