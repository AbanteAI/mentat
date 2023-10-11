from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from timeit import default_timer

from openai.error import InvalidRequestError, RateLimitError

from .code_context import CODE_CONTEXT
from .config_manager import CONFIG_MANAGER, user_config_path
from .errors import MentatError, UserError
from .llm_api import (
    COST_TRACKER,
    call_llm_api,
    count_tokens,
    get_prompt_token_count,
    is_model_available,
    model_context_size,
)
from .parsers.file_edit import FileEdit
from .parsers.parser import PARSER, Parser
from .session_stream import SESSION_STREAM, SessionStream

CONVERSATION: ContextVar[Conversation] = ContextVar("mentat:conversation")


class Conversation:
    max_tokens: int

    def __init__(self):
        config = CONFIG_MANAGER.get()
        parser = PARSER.get()

        self.model = config.model()
        self.messages = list[dict[str, str]]()

        prompt = parser.get_system_prompt()
        self.add_system_message(prompt)

    async def display_token_count(self):
        stream = SESSION_STREAM.get()
        parser = PARSER.get()
        code_context = CODE_CONTEXT.get()
        config = CONFIG_MANAGER.get()

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
        context_size = model_context_size(self.model)
        maximum_context = config.maximum_context()
        if maximum_context:
            if context_size:
                context_size = min(context_size, maximum_context)
            else:
                context_size = maximum_context
        tokens = count_tokens(
            await code_context.get_code_message(self.model, max_tokens=0),
            self.model,
        ) + count_tokens(prompt, self.model)

        if not context_size:
            raise MentatError(
                f"Context size for {self.model} is not known. Please set"
                f" maximum-context in {user_config_path}."
            )
        else:
            self.max_tokens = context_size
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
                f"Prompt and included files token count: {tokens} / {context_size}",
                color="cyan",
            )

    def add_system_message(self, message: str):
        self.messages.append({"role": "system", "content": message})

    def add_user_message(self, message: str):
        self.messages.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.messages.append({"role": "assistant", "content": message})

    async def _stream_model_response(
        self,
        stream: SessionStream,
        parser: Parser,
        messages: list[dict[str, str]],
    ):
        start_time = default_timer()
        try:
            response = await call_llm_api(messages, self.model)
            await stream.send(
                "Streaming... use control-c to interrupt the model at any point\n"
            )
            async with parser.interrupt_catcher():
                message, file_edits = await parser.stream_and_parse_llm_response(
                    response
                )
        except InvalidRequestError as e:
            raise MentatError(
                "Something went wrong - invalid request to OpenAI API. OpenAI"
                " returned:\n"
                + str(e)
            )
        except RateLimitError as e:
            raise UserError("OpenAI gave a rate limit error:\n" + str(e))

        time_elapsed = default_timer() - start_time
        return (message, file_edits, time_elapsed)

    async def get_model_response(self) -> list[FileEdit]:
        stream = SESSION_STREAM.get()
        code_context = CODE_CONTEXT.get()
        cost_tracker = COST_TRACKER.get()
        parser = PARSER.get()

        messages = self.messages.copy()

        # Rebuild code context with active code and available tokens
        conversation_history = "\n".join([m["content"] for m in messages])
        tokens = count_tokens(conversation_history, self.model)
        response_buffer = 1000
        code_message = await code_context.get_code_message(
            self.model,
            self.max_tokens - tokens - response_buffer,
        )
        messages.append({"role": "system", "content": code_message})

        print()
        await code_context.display_features()
        num_prompt_tokens = await get_prompt_token_count(messages, self.model)
        message, file_edits, time_elapsed = await self._stream_model_response(
            stream, parser, messages
        )
        await cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(message, self.model),
            self.model,
            time_elapsed,
        )

        transcript_logger = logging.getLogger("transcript")
        messages.append({"role": "assistant", "content": message})
        transcript_logger.info(json.dumps({"messages": messages}))

        self.add_assistant_message(message)
        return file_edits
