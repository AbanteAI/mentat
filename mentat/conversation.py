from __future__ import annotations

import json
import logging
from enum import Enum
from timeit import default_timer
from typing import TYPE_CHECKING

from openai.error import InvalidRequestError

from mentat.errors import MentatError
from mentat.llm_api import (
    call_llm_api,
    count_tokens,
    get_prompt_token_count,
    maximum_context_size,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream

if TYPE_CHECKING:
    from mentat.parsers.file_edit import FileEdit
    from mentat.parsers.parser import Parser


class MessageRole(Enum):
    System = "system"
    User = "user"
    Assistant = "assistant"


class Conversation:
    max_tokens: int

    def __init__(self):
        self.messages = list[dict[str, str]]()

        # This contain the messages the user actually sends and the messages the model output
        # along with a snapshot of exactly what the model got before that message
        self.literal_messages = list[tuple[str, list[dict[str, str]] | None]]()

    async def display_token_count(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context

        context_size = maximum_context_size()
        self.max_tokens = context_size
        conversation_history = "\n".join([m["content"] for m in self.get_messages()])
        tokens = count_tokens(
            await code_context.get_code_message("", max_tokens=0)
        ) + count_tokens(conversation_history)

        if tokens > context_size:
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
        self.messages.append({"role": role.value, "content": message})

    def get_messages(self) -> list[dict[str, str]]:
        """Returns the messages in the conversation. The system messsage may change throughout
        the conversation so it is important to access the messages through this method.
        """
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        if config.no_parser_prompt:
            return self.messages
        else:
            parser = config.parser
            prompt = parser.get_system_prompt()
            return [{"role": "system", "content": prompt}] + self.messages.copy()

    async def _stream_model_response(
        self,
        stream: SessionStream,
        parser: Parser,
        messages: list[dict[str, str]],
    ):
        start_time = default_timer()
        try:
            response = await call_llm_api(messages)
            stream.send(
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

        time_elapsed = default_timer() - start_time
        return (parsedLLMResponse, time_elapsed)

    async def get_model_response(self) -> list[FileEdit]:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        parser = session_context.config.parser
        cost_tracker = session_context.cost_tracker

        messages_snapshot = self.get_messages()

        # Rebuild code context with active code and available tokens
        conversation_history = "\n".join([m["content"] for m in messages_snapshot])
        tokens = count_tokens(conversation_history)
        response_buffer = 1000
        code_message = await code_context.get_code_message(
            messages_snapshot[-1]["content"],
            self.max_tokens - tokens - response_buffer,
        )
        messages_snapshot.append({"role": "system", "content": code_message})

        code_context.display_features()
        num_prompt_tokens = get_prompt_token_count(messages_snapshot)
        parsedLLMResponse, time_elapsed = await self._stream_model_response(
            stream, parser, messages_snapshot
        )
        cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(parsedLLMResponse.full_response),
            time_elapsed,
        )

        messages_snapshot.append(
            {"role": "assistant", "content": parsedLLMResponse.full_response}
        )
        self.add_model_message(parsedLLMResponse.full_response, messages_snapshot)
        return parsedLLMResponse.file_edits
