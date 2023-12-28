from typing import List

import attr
from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT


class ConfigCommand(Command, command_name="config"):
    @override
    async def apply(self, *args: str) -> None:
        from mentat.config import YamlConfig, update_config
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        yaml_config = YamlConfig()

        if len(args) == 0:
            stream.send("No config option specified", color="yellow")
        else:
            setting = args[0]
            if hasattr(yaml_config, setting):
                if len(args) == 1:
                    value = getattr(yaml_config, setting)
                    description = attr.fields_dict(type(yaml_config))[setting].metadata.get(
                        "description"
                    )
                    stream.send(f"{setting}: {value}")
                    if description:
                        stream.send(f"Description: {description}")
                elif len(args) == 2:
                    value = args[1]
                    if attr.fields_dict(type(yaml_config))[setting].metadata.get(
                        "no_midsession_change"
                    ):
                        stream.send(
                            f"Cannot change {setting} mid-session. Please restart"
                            " Mentat to change this setting.",
                            color="yellow",
                        )
                        return
                    try:
                        update_config({setting: value})
                        stream.send(f"{setting} set to {value}", color="green")
                    except (TypeError, ValueError):
                        stream.send(
                            f"Illegal value for {setting}: {value}", color="red"
                        )
                else:
                    stream.send("Too many arguments", color="yellow")
            else:
                stream.send(f"Unrecognized config option: {setting}", color="red")

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
        from mentat.config import YamlConfig

        if argument_position == 0:
            return YamlConfig.get_fields()
        elif argument_position == 1:
            setting = arguments[0]
            fields = attr.fields_dict(YamlConfig)
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
