from __future__ import annotations

import webbrowser
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

import attr

from mentat.errors import MentatError, UserError
from mentat.git_handler import commit
from mentat.include_files import print_invalid_path
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import Transcript, get_transcript_logs
from mentat.utils import create_viewer


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

    # Although we don't await anything inside an apply method currently, in the future we might
    # ask ther user or a model something, which would require apply to be async
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
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        stream.send(
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
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        git_root = session_context.git_root

        if len(args) == 0:
            stream.send("No files specified", color="yellow")
            return
        for file_path in args:
            included_paths, invalid_paths = code_context.include_file(
                Path(file_path).absolute()
            )
            for invalid_path in invalid_paths:
                print_invalid_path(invalid_path)
            for included_path in included_paths:
                rel_path = included_path.relative_to(git_root)
                stream.send(f"{rel_path} added to context", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Add files to the code context"


class ExcludeCommand(Command, command_name="exclude"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        git_root = session_context.git_root

        if len(args) == 0:
            stream.send("No files specified", color="yellow")
            return
        for file_path in args:
            excluded_paths, invalid_paths = code_context.exclude_file(
                Path(file_path).absolute()
            )
            for invalid_path in invalid_paths:
                print_invalid_path(invalid_path)
            for excluded_path in excluded_paths:
                rel_path = excluded_path.relative_to(git_root)
                stream.send(f"{rel_path} removed from context", color="red")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["file1", "file2", "..."]

    @classmethod
    def help_message(cls) -> str:
        return "Remove files from the code context"


class UndoCommand(Command, command_name="undo"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager

        errors = code_file_manager.history.undo()
        if errors:
            stream.send(errors)
        stream.send("Undo complete", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Undo the last change made by Mentat"


class UndoAllCommand(Command, command_name="undo-all"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager

        errors = code_file_manager.history.undo_all()
        if errors:
            stream.send(errors)
        stream.send("Undos complete", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Undo all changes made by Mentat"


class ClearCommand(Command, command_name="clear"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        conversation = session_context.conversation

        conversation.clear_messages()
        message = "Message history cleared"
        stream.send(message, color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Clear the current conversation's message history"


SEARCH_RESULT_BATCH_SIZE = 10


class SearchCommand(Command, command_name="search"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        git_root = session_context.git_root

        if len(args) == 0:
            stream.send("No search query specified", color="yellow")
            return
        try:
            query = " ".join(args)
            results = await code_context.search(query=query)
        except UserError as e:
            stream.send(str(e), color="red")
            return

        for i, (feature, score) in enumerate(results, start=1):
            label = feature.ref()
            if label.startswith(str(git_root)):
                label = label[len(str(git_root)) + 1 :]
            if feature.name:
                label += f' "{feature.name}"'
            stream.send(f"{i:3} | {score:.3f} | {label}")
            if i > 1 and i % SEARCH_RESULT_BATCH_SIZE == 0:
                # TODO: Required to avoid circular imports, but not ideal.
                from mentat.session_input import ask_yes_no

                stream.send("\nShow More results? ")
                if not await ask_yes_no(default_yes=True):
                    break

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["search_query"]

    @classmethod
    def help_message(cls) -> str:
        return "Semantic search of files in code context."


class ConversationCommand(Command, command_name="conversation"):
    hidden = True

    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        conversation = session_context.conversation

        logs = get_transcript_logs()

        viewer_path = create_viewer(
            [Transcript(timestamp="Current", messages=conversation.literal_messages)]
            + logs
        )
        webbrowser.open(f"file://{viewer_path.resolve()}")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Opens an html page showing the conversation as seen by Mentat so far"


class ContextCommand(Command, command_name="context"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        code_context = session_context.code_context

        code_context.display_context()

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Shows all files currently in Mentat's context"


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
