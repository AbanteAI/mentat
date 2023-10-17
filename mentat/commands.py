from __future__ import annotations

import webbrowser
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from mentat.code_file_manager import CODE_FILE_MANAGER
from mentat.conversation import CONVERSATION, MessageRole
from mentat.session_stream import SESSION_STREAM
from mentat.utils import create_viewer

from .code_context import CODE_CONTEXT
from .errors import MentatError
from .git_handler import commit


class Command(ABC):
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

    @classmethod
    def get_command_completions(cls) -> List[str]:
        return list(map(lambda name: "/" + name, cls.get_command_names()))

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
            commands = Command.get_command_names()
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
            invalid_paths = code_context.include_file(Path(file_path).absolute())
            for invalid_path in invalid_paths:
                await stream.send(
                    f"File path {invalid_path} is not text encoded, and was skipped.",
                    color="light_yellow",
                )
            if file_path not in invalid_paths:
                await stream.send(f"{file_path} added to context", color="green")

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
            code_context.exclude_file(Path(file_path).absolute())
            await stream.send(f"{file_path} removed from context", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Remove files from the code context"


class UndoCommand(Command, command_name="undo"):
    async def apply(self, *args: str) -> None:
        stream = SESSION_STREAM.get()
        code_file_manager = CODE_FILE_MANAGER.get()
        errors = code_file_manager.history.undo()
        if errors:
            await stream.send(errors)
        await stream.send("Undo complete", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Undo the last change made by Mentat"


class UndoAllCommand(Command, command_name="undo-all"):
    async def apply(self, *args: str) -> None:
        stream = SESSION_STREAM.get()
        code_file_manager = CODE_FILE_MANAGER.get()
        errors = code_file_manager.history.undo_all()
        if errors:
            await stream.send(errors)
        await stream.send("Undos complete", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Undo all changes made by Mentat"


class ClearCommand(Command, command_name="clear"):
    async def apply(self, *args: str) -> None:
        stream = SESSION_STREAM.get()
        conversation = CONVERSATION.get()
        # Only keep system messages (for now just the prompt)
        conversation.messages = [
            message
            for message in conversation.messages
            if message["role"] == MessageRole.System
        ]
        message = "Message history cleared"
        await stream.send(message, color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Clear the current conversation's message history"


class ConversationCommand(Command, command_name="conversation"):
    hidden = True

    async def apply(self, *args: str) -> None:
        conversation = CONVERSATION.get()
        viewer_path = create_viewer(conversation.literal_messages)
        webbrowser.open(f"file://{viewer_path.resolve()}")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Opens an html page showing the conversation as seen by Mentat so far"
