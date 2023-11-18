from __future__ import annotations

import json
import logging
from enum import Enum
from timeit import default_timer
from typing import TYPE_CHECKING

from openai.error import RateLimitError

from mentat.errors import MentatError
from mentat.llm_api import (
    call_llm_api,
    conversation_tokens,
    count_tokens,
    get_prompt_token_count,
    is_model_available,
    model_context_size,
)
from mentat.session_context import SESSION_CONTEXT

if TYPE_CHECKING:
    from mentat.parsers.file_edit import FileEdit


class MessageRole(Enum):
    System = "system"
    User = "user"
    Assistant = "assistant"


class Conversation:
    max_tokens: int

    def __init__(self):
        self._messages = list[dict[str, str]]()

        # This contain the messages the user actually sends and the messages the model output
        # along with a snapshot of exactly what the model got before that message
        self.literal_messages = list[tuple[str, list[dict[str, str]] | None]]()

    async def display_token_count(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        code_context = session_context.code_context

        if not is_model_available(config.model):
            raise MentatError(
                f"Model {config.model} is not available. Please try again with a"
                " different model."
            )
        if "gpt-4" not in config.model:
            stream.send(
                "Warning: Mentat has only been tested on GPT-4. You may experience"
                " issues with quality. This model may not be able to respond in"
                " mentat's edit format.",
                color="yellow",
            )
            if "gpt-3.5" not in config.model:
                stream.send(
                    "Warning: Mentat does not know how to calculate costs or context"
                    " size for this model.",
                    color="yellow",
                )

        context_size = model_context_size(config.model)
        maximum_context = config.maximum_context
        if maximum_context:
            if context_size:
                context_size = min(context_size, maximum_context)
            else:
                context_size = maximum_context

        messages = self.get_messages() + [
            {
                "role": MessageRole.System.value,
                "content": await code_context.get_code_message("", max_tokens=0),
            }
        ]
        tokens = conversation_tokens(
            messages,
            config.model,
        )

        if not context_size:
            raise MentatError(
                f"Context size for {config.model} is not known. Please set"
                " maximum-context with `/config maximum_context value`."
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
            stream.send(
                f"Warning: Included files are close to token limit ({tokens} /"
                f" {context_size}), you may not be able to have a long"
                " conversation.",
                color="red",
            )
        else:
            stream.send(
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
        self._messages.append({"role": role.value, "content": message})

    def get_messages(self) -> list[dict[str, str]]:
        """Returns the messages in the conversation. The system message may change throughout
        the conversation so it is important to access the messages through this method.
        """
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        if config.no_parser_prompt:
            return self._messages
        else:
            parser = config.parser
            prompt = parser.get_system_prompt()
            return [
                {"role": MessageRole.System.value, "content": prompt}
            ] + self._messages.copy()

    def clear_messages(self) -> None:
        """Clears the messages in the conversation"""
        self._messages = list[dict[str, str]]()

    async def _stream_model_response(
        self,
        messages: list[dict[str, str]],
        loading_multiplier: float = 0.0,
    ):
        start_time = default_timer()
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        parser = config.parser
        num_prompt_tokens = get_prompt_token_count(messages, config.model)
        if loading_multiplier:
            stream.send(
                "Sending query and context to LLM",
                channel="loading",
                progress=50 * loading_multiplier,
            )
        response = await call_llm_api(messages, config.model)
        if loading_multiplier:
            stream.send(
                None,
                channel="loading",
                progress=50 * loading_multiplier,
                terminate=True,
            )
        stream.send(f"Total token count: {num_prompt_tokens}", color="cyan")
        stream.send(
            "Streaming... use control-c to interrupt the model at any point\n"
        )
        async with parser.interrupt_catcher():
            parsedLLMResponse = await parser.stream_and_parse_llm_response(response)

        time_elapsed = default_timer() - start_time
        return (parsedLLMResponse, time_elapsed, num_prompt_tokens)

    async def get_model_response(self) -> list[FileEdit]:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        code_context = session_context.code_context
        cost_tracker = session_context.cost_tracker

        messages_snapshot = self.get_messages()

        # Rebuild code context with active code and available tokens
        tokens = conversation_tokens(messages_snapshot, config.model)
        response_buffer = 1000
        loading_multiplier = 1.0 if config.auto_context else 0.0
        try:
            code_message = await code_context.get_code_message(
                messages_snapshot[-1]["content"],
                self.max_tokens - tokens - response_buffer,
                loading_multiplier=0.5 * loading_multiplier,
            )
            messages_snapshot.append({"role": "system", "content": code_message})
            response = await self._stream_model_response(
                messages_snapshot,
                loading_multiplier=0.5 * loading_multiplier,
            )
            parsedLLMResponse, time_elapsed, num_prompt_tokens = response
        except RateLimitError:
            stream.send(
                "Rate limit recieved from OpenAI's servers using model"
                f' {config.model}.\nUse "/config model <model_name>" to switch to a'
                " different model.",
                color="light_red",
            )
            return []
        finally:
            if loading_multiplier:
                stream.send(None, channel="loading", terminate=True)
        cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(
                parsedLLMResponse.full_response, config.model, full_message=True
            ),
            config.model,
            time_elapsed,
        )

        messages_snapshot.append(
            {
                "role": MessageRole.Assistant.value,
                "content": parsedLLMResponse.full_response,
            }
        )
        self.add_model_message(parsedLLMResponse.full_response, messages_snapshot)
        return parsedLLMResponse.file_edits
