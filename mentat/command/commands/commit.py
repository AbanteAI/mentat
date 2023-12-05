from mentat.command.command import Command
from mentat.git_handler import commit


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
