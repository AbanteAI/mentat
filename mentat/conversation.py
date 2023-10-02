from timeit import default_timer

from openai.error import InvalidRequestError, RateLimitError

from mentat.parsers.file_edit import FileEdit
from mentat.parsers.parser import Parser

from .code_context import CodeContext
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager, user_config_path
from .errors import MentatError, UserError
from .llm_api import (
    CostTracker,
    call_llm_api,
    count_tokens,
    get_prompt_token_count,
    is_model_available,
    model_context_size,
)
from .session_stream import get_session_stream


class Conversation:
    def __init__(
        self,
        config: ConfigManager,
        cost_tracker: CostTracker,
        code_context: CodeContext,
        code_file_manager: CodeFileManager,
    ):
        self.cost_tracker = cost_tracker
        self.code_context = code_context
        self.code_file_manager = code_file_manager
        self.model = config.model()

        self.messages = list[dict[str, str]]()

    @classmethod
    async def create(
        cls,
        parser: Parser,
        config: ConfigManager,
        cost_tracker: CostTracker,
        code_context: CodeContext,
        code_file_manager: CodeFileManager,
    ):
        stream = get_session_stream()

        self = Conversation(config, cost_tracker, code_context, code_file_manager)

        if not is_model_available(self.model):
            raise MentatError(
                f"Model {self.model} is not available. Please try again with a"
                " different model."
            )
        if "gpt-4" not in self.model:
            await stream.send(
                "Warning: Mentat has only been tested on GPT-4. You may experience"
                " issues with quality. This model may not be able to respond in"
                " mentat's edit format.",
                color="yellow",
            )
            if "gpt-3.5" not in self.model:
                await stream.send(
                    "Warning: Mentat does not know how to calculate costs or context"
                    " size for this model.",
                    color="yellow",
                )

        prompt = parser.get_system_prompt()
        self.add_system_message(prompt)

        tokens = count_tokens(
            await code_context.get_code_message(
                self.model, self.code_file_manager, parser
            ),
            self.model,
        ) + count_tokens(prompt, self.model)
        context_size = model_context_size(self.model)
        maximum_context = config.maximum_context()
        if maximum_context:
            if context_size:
                context_size = min(context_size, maximum_context)
            else:
                context_size = maximum_context

        if not context_size:
            raise MentatError(
                f"Context size for {self.model} is not known. Please set"
                f" maximum-context in {user_config_path}."
            )
        if context_size and tokens > context_size:
            raise MentatError(
                f"Included files already exceed token limit ({tokens} /"
                f" {context_size}). Please try running again with a reduced"
                " number of files."
            )
        elif tokens + 1000 > context_size:
            await stream.send(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {context_size}), you may not be able to have a long"
                " conversation.",
                color="red",
            )
        else:
            await stream.send(
                f"File and prompt token count: {tokens} / {context_size}",
                color="cyan",
            )

        return self

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    async def _stream_model_response(
        self,
        parser: Parser,
        config: ConfigManager,
        messages: list[dict[str, str]],
    ):
        stream = get_session_stream()

        start_time = default_timer()
        try:
            response = await call_llm_api(messages, self.model)
            await stream.send(
                "Streaming... use control-c to interrupt the model at any point"
            )
            async with parser.interrupt_catcher():
                message, file_edits = await parser.stream_and_parse_llm_response(
                    response, self.code_file_manager, config
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

    async def get_model_response(
        self, parser: Parser, config: ConfigManager
    ) -> list[FileEdit]:
        messages = self.messages.copy()
        code_message = await self.code_context.get_code_message(
            self.model, self.code_file_manager, parser
        )
        messages.append({"role": "system", "content": code_message})

        num_prompt_tokens = await get_prompt_token_count(messages, self.model)
        message, file_edits, time_elapsed = await self._stream_model_response(
            parser, config, messages
        )
        await self.cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(message, self.model),
            self.model,
            time_elapsed,
        )

        self.add_assistant_message(message)
        return file_edits
