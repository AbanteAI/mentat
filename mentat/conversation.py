import asyncio
import logging
from timeit import default_timer

from openai.error import InvalidRequestError, RateLimitError
from termcolor import cprint

from mentat.errors import MentatError, UserError
from mentat.parsers.file_edit import FileEdit
from mentat.parsers.parser import Parser

from .code_file_manager import CodeFileManager
from .code_map import CodeMap
from .config_manager import ConfigManager
from .llm_api import (
    CostTracker,
    call_llm_api,
    check_model_availability,
    choose_model,
    count_tokens,
)


class Conversation:
    def __init__(
        self,
        parser: Parser,
        config: ConfigManager,
        cost_tracker: CostTracker,
        code_file_manager: CodeFileManager,
        code_map: CodeMap | None = None,
    ):
        prompt = parser.get_system_prompt()
        self.messages = list[dict[str, str]]()
        self.add_system_message(prompt)
        self.cost_tracker = cost_tracker
        self.code_file_manager = code_file_manager
        self.code_map = code_map
        self.allow_32k = check_model_availability(config.allow_32k())

        tokens = count_tokens(code_file_manager.get_code_message()) + count_tokens(
            prompt
        )
        self.token_limit = 32768 if self.allow_32k else 8192
        if tokens > self.token_limit:
            raise KeyboardInterrupt(
                f"Included files already exceed token limit ({tokens} /"
                f" {self.token_limit}). Please try running again with a reduced number"
                " of files."
            )
        elif tokens + 1000 > self.token_limit:
            cprint(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {self.token_limit}), you may not be able to have a long"
                " conversation.",
                "red",
            )
        else:
            cprint(
                f"File and prompt token count: {tokens} / {self.token_limit}", "cyan"
            )

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    def _get_system_message(self):
        messages = self.messages.copy()
        system_message = self.code_file_manager.get_code_message()

        if self.code_map:
            system_message_token_count = count_tokens(system_message)
            messages_token_count = 0
            for message in messages:
                messages_token_count += count_tokens(message["content"])
            token_buffer = 1000
            token_count = (
                system_message_token_count + messages_token_count + token_buffer
            )
            max_tokens_for_code_map = self.token_limit - token_count

            if self.code_map.token_limit:
                code_map_message_token_limit = min(
                    self.code_map.token_limit, max_tokens_for_code_map
                )
            else:
                code_map_message_token_limit = max_tokens_for_code_map

            code_map_message = self.code_map.get_message(
                token_limit=code_map_message_token_limit
            )
            if code_map_message:
                match (code_map_message.level):
                    case "signatures":
                        cprint_message_level = "full syntax tree"
                    case "no_signatures":
                        cprint_message_level = "partial syntax tree"
                    case "filenames":
                        cprint_message_level = "filepaths only"

                cprint_message = f"\nIncluding CodeMap ({cprint_message_level})"
                cprint(cprint_message, color="green")
                system_message += f"\n{code_map_message}"
            else:
                cprint_message = [
                    "\nExcluding CodeMap from system message.",
                    "Reason: not enough tokens available in model context.",
                ]
                cprint_message = "\n".join(cprint_message)
                cprint(cprint_message, color="yellow")
        return system_message

    async def _run_async_stream(
        self,
        parser: Parser,
        config: ConfigManager,
        messages: list[dict[str, str]],
        model: str,
    ) -> tuple[str, list[FileEdit]]:
        response = await call_llm_api(messages, model)
        # TODO once this becomes a separate parsing injectable, use injectable here
        message, file_edits = await parser.stream_and_parse_llm_response(
            response, self.code_file_manager, config
        )
        return message, file_edits

    def _handle_async_stream(
        self,
        parser: Parser,
        config: ConfigManager,
        messages: list[dict[str, str]],
        model: str,
    ) -> tuple[str, list[FileEdit], float]:
        start_time = default_timer()
        try:
            message, file_edits = asyncio.run(
                self._run_async_stream(parser, config, messages, model)
            )
        except InvalidRequestError as e:
            raise MentatError(
                "Something went wrong - invalid request to OpenAI API. OpenAI"
                " returned:\n"
                + str(e)
            )
        except RateLimitError as e:
            raise UserError("OpenAI gave a rate limit error:\n" + str(e))
        except KeyboardInterrupt:
            # TODO: Once the interface PR is merged, we will be sending signals down to the streaming
            # subroutine; the OriginalFormatParser needs to remove the latest change if it's incomplete
            # Previous code (which was here, will be in the subroutine after this):
            # if state.in_code_lines:
            #     state.code_changes = state.code_changes[:-1]
            print("\n\nInterrupted by user. Using the response up to this point.")
            logging.info("User interrupted response.")
            # TODO: This except won't be here after interface changes, and this won't be necessary
            message, file_edits = "", []

        time_elapsed = default_timer() - start_time
        return (message, file_edits, time_elapsed)

    def get_model_response(
        self, parser: Parser, config: ConfigManager
    ) -> list[FileEdit]:
        messages = self.messages.copy()

        system_message = self._get_system_message()
        messages.append({"role": "system", "content": system_message})
        model, num_prompt_tokens = choose_model(messages, self.allow_32k)

        message, file_edits, time_elapsed = self._handle_async_stream(
            parser, config, messages, model
        )
        self.cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(message),
            model,
            time_elapsed,
        )

        self.add_assistant_message(message)
        return file_edits
