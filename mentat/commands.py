from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class Command(ABC):
    _registered_commands = {}

    def __init_subclass__(cls, command_name: str | None) -> None:
        if command_name is not None:
            Command._registered_commands[command_name] = cls

    @classmethod
    def create_command(cls, command_name: str) -> Command:
        if command_name not in cls._registered_commands:
            return InvalidCommand()
        else:
            return cls._registered_commands[command_name]()

    @classmethod
    def get_command_completions(cls) -> Iterable[str]:
        return list(map(lambda name: "/" + name, cls._registered_commands))

    @abstractmethod
    def apply(self) -> None:
        pass


class InvalidCommand(Command, command_name=None):
    def apply(self):
        print("INVALID")


class HelpCommand(Command, command_name="help"):
    def apply(self):
        print("HELP")


class CommitCommand(Command, command_name="commit"):
    def apply(self):
        print("COMMIT")
