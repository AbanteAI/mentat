from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.git_handler import commit


class CommitCommand(Command, command_name="commit"):
    default_message = "Automatic commit"

    @override
    async def apply(self, *args: str) -> None:
        if args:
            commit(args[0])
        else:
            commit(self.__class__.default_message)

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("optional", "commit message")]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Commit all unstaged and staged changes to git."
