from __future__ import annotations

import json
import logging
from timeit import default_timer
from typing import TYPE_CHECKING

from openai.error import InvalidRequestError

from mentat.errors import MentatError
from mentat.llm_api import (
    call_llm_api,
    count_tokens,
    get_prompt_token_count,
    is_model_available,
    model_context_size,
)
from mentat.message import Message, MessageRole
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream

if TYPE_CHECKING:
    from mentat.parsers.file_edit import FileEdit
    from mentat.parsers.parser import Parser


class Conversation:
    max_tokens: int

    def __init__(self):
        self._messages = list[Message]()

        # This contain the messages the user actually sends and the messages the model output
        # along with a snapshot of exactly what the model got before that message
        self.literal_messages = list[tuple[Message, list[Message] | None]]()

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
        tokens = (
            count_tokens(
                await code_context.get_code_message("", max_tokens=0),
                config.model,
            )
            + self.token_count()
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
    def add_message(
        self, message: Message, messages_snapshot: list[Message] | None = None
    ):
        """Used for adding messages to the models conversation"""
        transcript_logger = logging.getLogger("transcript")
        transcript_logger.info(json.dumps((message, messages_snapshot), default=str))
        self.literal_messages.append((message, None))
        self._messages.append(message)

    def get_messages(self) -> list[Message]:
        """Returns the messages in the conversation. The system message may change throughout
        the conversation so it is important to access the messages through this method.
        """
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        if config.no_parser_prompt:
            return self._messages.copy()
        else:
            parser = config.parser
            prompt = parser.get_system_prompt()
            return [Message(MessageRole.System, prompt)] + self._messages.copy()

    def clear_messages(self) -> None:
        """Clears the messages in the conversation"""
        self._messages = list[Message]()

    def token_count(self) -> int:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        tokens = 0
        for message in self.get_messages():
            tokens += count_tokens(message, config.model)
        return tokens

    async def _stream_model_response(
        self,
        stream: SessionStream,
        parser: Parser,
        messages: list[Message],
    ):
        start_time = default_timer()
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        llm_messages = []
        for message in messages:
            llm_messages.append(message.llm_view())  # type: ignore
        try:
            response = await call_llm_api(llm_messages, config.model)
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
        config = session_context.config
        code_context = session_context.code_context
        parser = config.parser
        cost_tracker = session_context.cost_tracker

        messages_snapshot = self.get_messages()

        # Rebuild code context with active code and available tokens
        tokens = self.token_count()
        response_buffer = 1000
        code_message = await code_context.get_code_message(
            messages_snapshot[-1].text,
            self.max_tokens - tokens - response_buffer,
        )
        messages_snapshot.append(Message(MessageRole.System, code_message))

        code_context.display_features()
        num_prompt_tokens = get_prompt_token_count(messages_snapshot, config.model)
        parsedLLMResponse, time_elapsed = await self._stream_model_response(
            stream, parser, messages_snapshot
        )
        cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            count_tokens(parsedLLMResponse.full_response, config.model),
            config.model,
            time_elapsed,
        )

        message = Message(MessageRole.System, parsedLLMResponse.full_response)
        messages_snapshot.append(message)
        self.add_message(message, messages_snapshot)
        return parsedLLMResponse.file_edits
