from typing import List, Set

from termcolor import colored
from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.errors import UserError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path

SEARCH_RESULT_BATCH_SIZE = 10


def _parse_include_input(user_input: str, max_num: int) -> Set[int] | None:
    nums: Set[int] = set()
    for part in user_input.split():
        left_right = part.split("-")
        if len(left_right) > 2:
            return None
        elif len(left_right) == 2:
            if not left_right[0].isdigit() or not left_right[1].isdigit():
                return None
            nums.update(range(int(left_right[0]), int(left_right[1]) + 1))
        else:
            if not part.isdigit():
                return None
            nums.add(int(part))
    nums = set(num for num in nums if num > 0 and num <= max_num)
    if not nums:
        return None
    return nums


class SearchCommand(Command, command_name="search"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        config = session_context.config

        if len(args) == 0:
            stream.send("No search query specified", style="warning")
            return
        try:
            query = " ".join(args)
            results = await code_context.search(query=query)
        except UserError as e:
            stream.send(str(e), style="error")
            return

        cumulative_tokens = 0
        for i, (feature, _) in enumerate(results, start=1):
            prefix = "\n   "

            file_name = feature.rel_path(session_context.cwd)
            file_name = colored(file_name, "blue", attrs=["bold"])
            file_name += colored(feature.interval_string(), "light_cyan")

            tokens = feature.count_tokens(config.model)
            cumulative_tokens += tokens
            tokens_str = colored(f"  ({tokens} tokens)", "yellow")
            file_name += tokens_str

            name = []
            if feature.name:
                name = feature.name.split(",")
                name = [
                    f"{'└' if i == len(name) - 1 else '├'}─ {colored(n, 'cyan')}"
                    for i, n in enumerate(name)
                ]

            message = f"{str(i).ljust(3)}" + prefix.join([file_name] + name + [""])
            stream.send(message)
            if i > 1 and i % SEARCH_RESULT_BATCH_SIZE == 0:
                # Required to avoid circular imports, but not ideal.
                from mentat.session_input import collect_user_input

                stream.send(
                    "(Y/n) for more results or to exit search mode.\nResults to"
                    ' include in context: (eg: "1 3 4" or "1-4")'
                )
                user_input: str = (await collect_user_input(plain=True)).data.strip()
                while user_input.lower() not in "yn":
                    to_include = _parse_include_input(user_input, i)
                    if to_include is not None:
                        features = [results[index - 1][0] for index in to_include]
                        included_paths = code_context.include_features(features)
                        for included_path in included_paths:
                            rel_path = get_relative_path(
                                included_path, session_context.cwd
                            )
                            stream.send(f"{rel_path} added to context", style="success")
                    else:
                        stream.send("(Y/n)", style="input")
                    user_input: str = (
                        await collect_user_input(plain=True)
                    ).data.strip()
                if user_input.lower() == "n":
                    stream.send("Exiting search mode...", style="input")
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
