from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from mentat.session_stream import SESSION_STREAM

from .code_context import CODE_CONTEXT
from .code_file import CodeFile
from .errors import MentatError
from .git_handler import commit


class Command(ABC):
    # Unfortunately, Command isn't defined here yet, so even with annotations we need quotation marks
    _registered_commands = dict[str, type["Command"]]()

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
    def get_command_completions(cls) -> List[str]:
        return list(map(lambda name: "/" + name, cls._registered_commands))

    @abstractmethod
    async def apply(self, *args: str) -> None:
        pass

    # TODO: make more robust way to specify arguments for commands
    @classmethod
    @abstractmethod
    def argument_names(cls) -> list[str]:
        pass

    @classmethod
    @abstractmethod
    def help_message(cls) -> str:
        pass


class InvalidCommand(Command, command_name=None):
    def __init__(self, invalid_name: str):
        self.invalid_name = invalid_name

    async def apply(self, *args: str) -> None:
        await SESSION_STREAM.get().send(
            f"{self.invalid_name} is not a valid command. Use /help to see a list of"
            " all valid commands",
            color="light_yellow",
        )

    @classmethod
    def argument_names(cls) -> list[str]:
        raise MentatError("Argument names called on invalid command")

    @classmethod
    def help_message(cls) -> str:
        raise MentatError("Help message called on invalid command")


help_message_width = 60


class HelpCommand(Command, command_name="help"):
    async def apply(self, *args: str) -> None:
        stream = SESSION_STREAM.get()

        if not args:
            commands = Command._registered_commands.keys()
        else:
            commands = args
        for command_name in commands:
            if command_name not in Command._registered_commands:
                await stream.send(
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
                await stream.send(message)

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Displays this message"


class CommitCommand(Command, command_name="commit"):
    default_message = "Automatic commit"

    async def apply(self, *args: str) -> None:
        if args:
            commit(args[0])
        else:
            commit(self.__class__.default_message)

    @classmethod
    def argument_names(cls) -> list[str]:
        return [f"commit_message={cls.default_message}"]

    @classmethod
    def help_message(cls) -> str:
        return "Commits all of your unstaged and staged changes to git"


class IncludeCommand(Command, command_name="include"):
    async def apply(self, *args: str) -> None:
        stream = SESSION_STREAM.get()
        code_context = CODE_CONTEXT.get()

        if len(args) == 0:
            await stream.send("No files specified\n", color="yellow")
            return
        for file_path in args:
            code_file = CodeFile(file_path)
            await code_context.include_file(code_file)

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Add files to the code context"


class ExcludeCommand(Command, command_name="exclude"):
    async def apply(self, *args: str) -> None:
        stream = SESSION_STREAM.get()
        code_context = CODE_CONTEXT.get()

        if len(args) == 0:
            await stream.send("No files specified\n", color="yellow")
            return
        for file_path in args:
            code_file = CodeFile(file_path)
            await code_context.exclude_file(code_file)

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Remove files from the code context"
