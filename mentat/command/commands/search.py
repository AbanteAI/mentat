from mentat.command.command import Command
from mentat.errors import UserError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path

SEARCH_RESULT_BATCH_SIZE = 10


class SearchCommand(Command, command_name="search"):
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        config = session_context.config

        if len(args) == 0:
            stream.send("No search query specified", color="yellow")
            return
        try:
            query = " ".join(args)
            results = await code_context.search(query=query)
        except UserError as e:
            stream.send(str(e), color="red")
            return

        cumulative_tokens = 0
        for i, (feature, score) in enumerate(results, start=1):
            i_str = f"{i:3}"
            score_str = f"{score:.3f}"

            label = feature.ref()
            label = label.removeprefix(str(session_context.cwd) + "/")
            if feature.name:
                label += f' "{feature.name}"'

            tokens = feature.count_tokens(config.model)
            cumulative_tokens += tokens

            tokens_str = f"{tokens} Tokens"
            cumulative_tokens_str = f"{cumulative_tokens} Cumulative Tokens"

            message = " | ".join(
                [i_str, score_str, tokens_str, cumulative_tokens_str, label]
            )
            stream.send(message)
            if i > 1 and i % SEARCH_RESULT_BATCH_SIZE == 0:
                # TODO: Required to avoid circular imports, but not ideal.
                from mentat.session_input import collect_user_input

                stream.send(
                    "\nEnter (Y) for more results, (n) to exit search mode, or a number"
                    " to add all features above that number to context."
                )
                user_input: str = (await collect_user_input(plain=True)).data.strip()
                while not (
                    (user_input.isdigit() and int(user_input) > 0)
                    or (user_input.lower() in "yn")
                ):
                    stream.send("(Y/n/number)")
                    user_input: str = (
                        await collect_user_input(plain=True)
                    ).data.strip()

                if not user_input or user_input.lower() == "y":
                    continue
                elif user_input.lower() == "n":
                    break
                else:
                    index = min(int(user_input), len(results))
                    for feat, _ in results[:index]:
                        included_paths = code_context.include(feat.ref())
                        for included_path in included_paths:
                            rel_path = get_relative_path(
                                included_path, session_context.cwd
                            )
                            stream.send(f"{rel_path} added to context", color="green")
                    break

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["search_query"]

    @classmethod
    def help_message(cls) -> str:
        return "Semantic search of files in code context."
