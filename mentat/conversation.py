from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from enum import Enum
from timeit import default_timer

from openai.error import InvalidRequestError, RateLimitError

from mentat.parsers.file_edit import FileEdit
from mentat.parsers.parser import PARSER, Parser
from tests.conftest import SessionStream

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
from .session_stream import SESSION_STREAM

CONVERSATION: ContextVar[Conversation] = ContextVar("mentat:conversation")


class MessageRole(Enum):
    System = "system"
    User = "user"
    Assistant = "assistant"


class Conversation:
    max_tokens: int

    def __init__(self):
        config = CONFIG_MANAGER.get()
        parser = PARSER.get()

        self.model = config.model()
        self.messages = list[dict[str, str]]()

        # This contain the messages the user actually sends and the messages the model output
        # along with a snapshot of exactly what the model got before that message
        self.literal_messages = list[tuple[str, list[dict[str, str]] | None]]()

        prompt = parser.get_system_prompt()
        self.add_message(MessageRole.System, prompt)

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
            await code_context.get_code_message("", self.model, max_tokens=0),
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

    # The transcript logger logs tuples containing the actual message sent by the user or LLM
    # and (for LLM messages) the LLM conversation that led to that LLM response
    def add_user_message(self, message: str):
        """Used for actual user input messages"""
        transcript_logger = logging.getLogger("transcript")
        transcript_logger.info(json.dumps((message, None)))
        self.literal_messages.append((message, None))
        self.add_message(MessageRole.User, message)

    def add_model_message(self, message: str, messages_snapshot: list[dict[str, str]]):
        """Used for actual model output messages"""
        transcript_logger = logging.getLogger("transcript")
        transcript_logger.info(json.dumps((message, messages_snapshot)))
        self.literal_messages.append((message, messages_snapshot))
        self.add_message(MessageRole.Assistant, message)

    def add_message(self, role: MessageRole, message: str):
        """Used for adding messages to the models conversation"""
        self.messages.append({"role": role.value, "content": message})

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
                parsedLLMResponse = await parser.stream_and_parse_llm_response(response)
        except InvalidRequestError as e:
            raise MentatError(
                "Something went wrong - invalid request to OpenAI API. OpenAI"
                " returned:\n"
                + str(e)
            )
        except RateLimitError as e:
            raise UserError("OpenAI gave a rate limit error:\n" + str(e))

        time_elapsed = default_timer() - start_time
        return (parsedLLMResponse, time_elapsed)

    async def get_model_response(self) -> list[FileEdit]:
        stream = SESSION_STREAM.get()
        code_context = CODE_CONTEXT.get()
        cost_tracker = COST_TRACKER.get()
        parser = PARSER.get()

        messages_snapshot = self.messages.copy()

        # Rebuild code context with active code and available tokens
        conversation_history = "\n".join([m["content"] for m in messages_snapshot])
        tokens = count_tokens(conversation_history, self.model)
        response_buffer = 1000
        code_message = await code_context.get_code_message(
            messages_snapshot[-1]["content"],
            self.model,
            self.max_tokens - tokens - response_buffer,
        )
        messages_snapshot.append({"role": "system", "content": code_message})

        await code_context.display_features()
        num_prompt_tokens = await get_prompt_token_count(messages_snapshot, self.model)
        parsedLLMResponse, time_elapsed = await self._stream_model_response(
            stream, parser, messages_snapshot
        )
        await cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(parsedLLMResponse.full_response, self.model),
            self.model,
            time_elapsed,
        )

        messages_snapshot.append(
            {"role": "assistant", "content": parsedLLMResponse.full_response}
        )
        self.add_model_message(parsedLLMResponse.full_response, messages_snapshot)
        return parsedLLMResponse.file_edits
