from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from termcolor import cprint

from .errors import MentatError
from .git_handler import commit

help_message_width = 20


class Command(ABC):
    _registered_commands = {}

    def __init_subclass__(cls, command_name: str | None) -> None:
        if command_name is not None:
            Command._registered_commands[command_name] = cls

    @classmethod
    def create_command(cls, command_name: str) -> Command:
        if command_name not in cls._registered_commands:
            return InvalidCommand(command_name)
        else:
            return cls._registered_commands[command_name]()

    @classmethod
    def get_command_completions(cls) -> Iterable[str]:
        return list(map(lambda name: "/" + name, cls._registered_commands))

    @classmethod
    @abstractmethod
    def help_message(cls) -> str:
        pass

    @abstractmethod
    def apply(self) -> None:
        pass


class InvalidCommand(Command, command_name=None):
    def __init__(self, invalid_name):
        self.invalid_name = invalid_name

    def apply(self) -> None:
        cprint(
            f"{self.invalid_name} is not a valid command. Use /help to see a list of"
            " all valid commands",
            color="light_yellow",
        )

    @classmethod
    def help_message(cls) -> str:
        raise MentatError("Help message called on invalid command")


class HelpCommand(Command, command_name="help"):
    def apply(self) -> None:
        for command_name, command_class in Command._registered_commands.items():
            print(
                f"/{command_name}".ljust(help_message_width),
                command_class.help_message(),
            )

    @classmethod
    def help_message(cls) -> str:
        return "Displays this message"


class CommitCommand(Command, command_name="commit"):
    def apply(self) -> None:
        commit()

    @classmethod
    def help_message(cls) -> str:
        return "Commits all of your unstaged and staged changes to git"
