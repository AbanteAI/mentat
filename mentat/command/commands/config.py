import attr

from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class ConfigCommand(Command, command_name="config"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        if len(args) == 0:
            stream.send("No config option specified", color="yellow")
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
                            color="yellow",
                        )
                        return
                    try:
                        setattr(config, setting, value)
                        stream.send(f"{setting} set to {value}", color="green")
                    except (TypeError, ValueError):
                        stream.send(
                            f"Illegal value for {setting}: {value}", color="red"
                        )
                else:
                    stream.send("Too many arguments", color="yellow")
            else:
                stream.send(f"Unrecognized config option: {setting}", color="red")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["setting", "value"]

    @classmethod
    def help_message(cls) -> str:
        return "Set a configuration option or omit value to see current value."
