from typing import List

import attr
from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class ConfigCommand(Command, command_name="config"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        if len(args) == 0:
            stream.send("No config option specified", style="warning")
        else:
            setting = args[0]
            if hasattr(config, setting):
                if len(args) == 1:
                    value = getattr(config, setting)
                    description = attr.fields_dict(type(config))[setting].metadata.get(
                        "description"
                    )
                    stream.send(f"{setting}: {value}")
                    if description:
                        stream.send(f"Description: {description}")
                elif len(args) == 2:
                    value = args[1]
                    if attr.fields_dict(type(config))[setting].metadata.get(
                        "no_midsession_change"
                    ):
                        stream.send(
                            f"Cannot change {setting} mid-session. Please restart"
                            " Mentat to change this setting.",
                            style="warning",
                        )
                        return
                    try:
                        setattr(config, setting, value)
                        stream.send(f"{setting} set to {value}", style="success")
                    except (TypeError, ValueError):
                        stream.send(
                            f"Illegal value for {setting}: {value}", style="error"
                        )
                else:
                    stream.send("Too many arguments", style="warning")
            else:
                stream.send(f"Unrecognized config option: {setting}", style="error")

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
        # Dodge circular imports
        from mentat.config import Config

        if argument_position == 0:
            return Config.get_fields()
        elif argument_position == 1:
            setting = arguments[0]
            fields = attr.fields_dict(Config)
            if setting in fields:
                return fields[setting].metadata.get("auto_completions", [])
            else:
                return []
        else:
            return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Show or set a config option's value."
