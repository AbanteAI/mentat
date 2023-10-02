import asyncio
from timeit import default_timer

from openai.error import InvalidRequestError, RateLimitError
from termcolor import cprint

from mentat.config_manager import ConfigManager, user_config_path
from mentat.errors import MentatError, UserError
from mentat.llm_api import (
    CostTracker,
    call_llm_api,
    count_tokens,
    get_prompt_token_count,
    is_model_available,
    model_context_size,
)
from mentat.parsers.file_edit import FileEdit
from mentat.parsers.parser import Parser

from .code_context import CodeContext
from .code_file_manager import CodeFileManager


class Conversation:
    def __init__(
        self,
        parser: Parser,
        config: ConfigManager,
        cost_tracker: CostTracker,
        code_context: CodeContext,
        code_file_manager: CodeFileManager,
    ):
        self.messages = list[dict[str, str]]()
        prompt = parser.get_system_prompt()
        self.add_system_message(prompt)
        self.cost_tracker = cost_tracker
        self.code_context = code_context
        self.code_file_manager = code_file_manager
        self.model = config.model()
        if not is_model_available(self.model):
            raise KeyboardInterrupt(
                f"Model {self.model} is not available. Please try again with a"
                " different model."
            )
        if "gpt-4" not in self.model:
            cprint(
                "Warning: Mentat has only been tested on GPT-4. You may experience"
                " issues with quality. This model may not be able to respond in"
                " mentat's edit format.",
                color="yellow",
            )
            if "gpt-3.5" not in self.model:
                cprint(
                    "Warning: Mentat does not know how to calculate costs or context"
                    " size for this model.",
                    color="yellow",
                )

        context_size = model_context_size(self.model)
        maximum_context = config.maximum_context()
        if maximum_context:
            if context_size:
                context_size = min(context_size, maximum_context)
            else:
                context_size = maximum_context
        tokens = count_tokens(
            code_context.get_code_message(self.model, self.code_file_manager, max_tokens=0), 
            self.model
        ) + count_tokens(prompt, self.model)

        if not context_size:
            raise KeyboardInterrupt(
                f"Context size for {self.model} is not known. Please set"
                f" maximum-context in {user_config_path}."
            )
        else:
            self.max_tokens = context_size
        if context_size and tokens > context_size:
            raise KeyboardInterrupt(
                f"Included files already exceed token limit ({tokens} /"
                f" {context_size}). Please try running again with a reduced"
                " number of files."
            )
        elif tokens + 1000 > context_size:
            cprint(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {context_size}), you may not be able to have a long"
                " conversation.",
                "red",
            )
        else:
            cprint(
                f"Prompt and included files token count: {tokens} / {context_size}",
                "cyan",
            )

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    async def _run_async_stream(
        self, parser: Parser, config: ConfigManager, messages: list[dict[str, str]]
    ) -> tuple[str, list[FileEdit]]:
        response = await call_llm_api(messages, self.model)
        with parser.interrupt_catcher():
            print("\nStreaming...  use control-c to interrupt the model at any point\n")
            message, file_edits = await parser.stream_and_parse_llm_response(
                response, self.code_file_manager, config
            )
        return message, file_edits

    def _handle_async_stream(
        self,
        parser: Parser,
        config: ConfigManager,
        messages: list[dict[str, str]],
    ) -> tuple[str, list[FileEdit], float]:
        start_time = default_timer()
        try:
            message, file_edits = asyncio.run(
                self._run_async_stream(parser, config, messages)
            )
        except InvalidRequestError as e:
            raise MentatError(
                "Something went wrong - invalid request to OpenAI API. OpenAI"
                " returned:\n" + str(e)
            )
        except RateLimitError as e:
            raise UserError("OpenAI gave a rate limit error:\n" + str(e))

        time_elapsed = default_timer() - start_time
        return (message, file_edits, time_elapsed)

    def get_model_response(
        self, parser: Parser, config: ConfigManager
    ) -> list[FileEdit]:
        messages = self.messages.copy()

        # Rebuild code context with active code and available tokens
        conversation_history = "\n".join([m["content"] for m in messages])
        tokens = count_tokens(conversation_history, self.model)
        response_buffer = 1000
        code_message = self.code_context.get_code_message(
            self.model, self.code_file_manager, self.max_tokens - tokens - response_buffer
        )
        messages.append({"role": "system", "content": code_message})

        print()
        self.code_context.display_features()
        num_prompt_tokens = get_prompt_token_count(messages, self.model)
        message, file_edits, time_elapsed = self._handle_async_stream(
            parser, config, messages
        )
        self.cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(message, self.model),
            self.model,
            time_elapsed,
        )

        self.add_assistant_message(message)
        return file_edits
