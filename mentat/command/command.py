from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Literal

import attr

from mentat.errors import MentatError
from mentat.session_context import SESSION_CONTEXT


@attr.define
class CommandArgument:
    # Required: <arg>, Optional: [arg], Literal: arg
    arg_type: Literal["required", "optional", "literal"] = attr.field()
    # Multiple descriptions will be separated with |: desc1|desc2
    description: str | List[str] = attr.field()
    # Repeatable arguments will be followed with ...: <arg1> ...
    repeatable: bool = attr.field(default=False)


class Command(ABC):
    """
    Base Command class. To create a new command, extend this class, provide a command_name,
    and import the class in commands.__init__.py so that it is initialized on startup.
    """

    # Unfortunately, Command isn't defined here yet, so even with annotations we need quotation marks
    _registered_commands = dict[str, type["Command"]]()
    hidden = False

    def __init_subclass__(cls, command_name: str | None) -> None:
        if command_name is not None:
            Command._registered_commands[command_name] = cls

    @classmethod
    def create_command(cls, command_name: str) -> Command:
        if command_name not in cls._registered_commands:
            return InvalidCommand(command_name)

        command_cls = cls._registered_commands[command_name]
        return command_cls()

    @classmethod
    def get_command_names(cls) -> list[str]:
        return [
            name
            for name, command in cls._registered_commands.items()
            if not command.hidden
        ]

    @abstractmethod
    async def apply(self, *args: str) -> None:
        pass

    @classmethod
    @abstractmethod
    def arguments(cls) -> List[CommandArgument]:
        pass

    @classmethod
    @abstractmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        """
        Returns a list of possible completions for the argument in the specified position (0-indexed)
        given the previous arguments
        """
        pass

    @classmethod
    @abstractmethod
    def help_message(cls) -> str:
        pass


class InvalidCommand(Command, command_name=None):
    def __init__(self, invalid_name: str):
        self.invalid_name = invalid_name

    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        stream.send(
            f"{self.invalid_name} is not a valid command. Use /help to see a list of"
            " all valid commands",
            style="warning",
        )

    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        raise MentatError("Argument names called on invalid command")

    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        raise MentatError("Help message called on invalid command")
