from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class ConfigCommand(Command, command_name="config"):
    @override
    async def apply(self, *args: str) -> None:
        from mentat.config import get_config, mid_session_config, update_config

        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        if len(args) == 0:
            stream.send("No config option specified", color="yellow")
        elif len(args) == 1 or len(args) == 2:

            setting = args[0]
            if setting in mid_session_config:
                if len(args) == 2:
                    value = args[1]
                    update_config(setting=setting, value=value)
                else:
                    get_config(setting=setting)
            else:
                stream.send(f"Unrecognized config option: {setting}", color="red")
        else:
            stream.send("Too many arguments", color="yellow")

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [
            CommandArgument("required", "setting"),
            CommandArgument("optional", "value"),
        ]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:

        if argument_position == 0:
            return [
                "model",
                "temperature",
                "prompt_type",
                "format",
                "maximum_context",
                "auto_context_tokens",
            ]
        elif argument_position == 1:
            # TODO: Figure out a better way of doing this.
            return []
        else:
            return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Show or set a config option's value."
