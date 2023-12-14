from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.errors import UserError
from mentat.session_context import SESSION_CONTEXT

SEARCH_RESULT_BATCH_SIZE = 10


class SearchCommand(Command, command_name="search"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

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
            if label.startswith(str(session_context.cwd)):
                label = label[len(str(session_context.cwd)) + 1 :]
            if feature.name:
                label += f' "{feature.name}"'
            stream.send(f"{i:3} | {score:.3f} | {label}")
            if i > 1 and i % SEARCH_RESULT_BATCH_SIZE == 0:
                # TODO: Required to avoid circular imports, but not ideal.
                from mentat.session_input import ask_yes_no

                stream.send("\nShow More results? ")
                if not await ask_yes_no(default_yes=True):
                    break

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("required", "query")]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        ctx = SESSION_CONTEXT.get()

        return [
            completion["display"] or completion["content"]
            for completion in ctx.auto_completer.get_file_completions(arguments[-1])
        ]

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Search files in context semantically with embeddings."
