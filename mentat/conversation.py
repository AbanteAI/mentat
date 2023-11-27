from __future__ import annotations

import json
import logging
from timeit import default_timer
from typing import TYPE_CHECKING

from openai import RateLimitError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.errors import MentatError
from mentat.llm_api_handler import conversation_tokens, count_tokens, model_context_size
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import ModelMessage, TranscriptMessage, UserMessage
from mentat.utils import add_newline

if TYPE_CHECKING:
    from mentat.parsers.file_edit import FileEdit


class Conversation:
    max_tokens: int

    def __init__(self):
        self._messages = list[ChatCompletionMessageParam]()

        # This contains a list of messages used for transcripts
        self.literal_messages = list[TranscriptMessage]()

    async def display_token_count(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        code_context = session_context.code_context
        llm_api_handler = session_context.llm_api_handler

        if not await llm_api_handler.is_model_available(config.model):
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
            ChatCompletionSystemMessageParam(
                role="system",
                content=await code_context.get_code_message("", max_tokens=0),
            )
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
        transcript_logger.info(
            json.dumps(UserMessage(message=message, prior_messages=None))
        )
        self.literal_messages.append(UserMessage(message=message, prior_messages=None))
        self.add_message(ChatCompletionUserMessageParam(role="user", content=message))

    def add_model_message(
        self, message: str, messages_snapshot: list[ChatCompletionMessageParam]
    ):
        """Used for actual model output messages"""
        transcript_logger = logging.getLogger("transcript")
        transcript_logger.info(
            json.dumps(ModelMessage(message=message, prior_messages=messages_snapshot))
        )
        self.literal_messages.append(
            ModelMessage(message=message, prior_messages=messages_snapshot)
        )
        self.add_message(
            ChatCompletionAssistantMessageParam(role="assistant", content=message)
        )

    def add_message(self, message: ChatCompletionMessageParam):
        """Used for adding messages to the models conversation"""
        self._messages.append(message)

    def get_messages(self) -> list[ChatCompletionMessageParam]:
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
            prompt_message: ChatCompletionMessageParam = (
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=prompt,
                )
            )
            return [prompt_message] + self._messages.copy()

    def clear_messages(self) -> None:
        """Clears the messages in the conversation"""
        self._messages = list[ChatCompletionMessageParam]()

    async def _stream_model_response(
        self,
        messages: list[ChatCompletionMessageParam],
        loading_multiplier: float = 0.0,
    ):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        parser = config.parser
        llm_api_handler = session_context.llm_api_handler

        start_time = default_timer()

        num_prompt_tokens = conversation_tokens(messages, config.model)
        token_buffer = 500
        context_size = model_context_size(config.model)
        if context_size:
            if num_prompt_tokens > context_size - token_buffer:
                stream.send(
                    f"Warning: {config.model} has a maximum context length of"
                    f" {context_size} tokens. Attempting to run anyway:",
                    color="yellow",
                )

        if loading_multiplier:
            stream.send(
                "Sending query and context to LLM",
                channel="loading",
                progress=50 * loading_multiplier,
            )
        response = await llm_api_handler.call_llm_api(
            messages, config.model, stream=True
        )
        if loading_multiplier:
            stream.send(
                None,
                channel="loading",
                progress=50 * loading_multiplier,
                terminate=True,
            )

        stream.send(f"Total token count: {num_prompt_tokens}", color="cyan")
        stream.send("Streaming... use control-c to interrupt the model at any point\n")
        async with parser.interrupt_catcher():
            parsed_llm_response = await parser.stream_and_parse_llm_response(
                add_newline(response)
            )

        time_elapsed = default_timer() - start_time
        return (parsed_llm_response, time_elapsed, num_prompt_tokens)

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
            prompt = messages_snapshot[-1]["content"]
            code_message = await code_context.get_code_message(
                (
                    # Prompt can be image as well as text
                    prompt
                    if isinstance(prompt, str)
                    else ""
                ),
                self.max_tokens - tokens - response_buffer,
                loading_multiplier=0.5 * loading_multiplier,
            )
            messages_snapshot.append(
                ChatCompletionSystemMessageParam(role="system", content=code_message)
            )
            response = await self._stream_model_response(
                messages_snapshot,
                loading_multiplier=0.5 * loading_multiplier,
            )
            parsed_llm_response, time_elapsed, num_prompt_tokens = response
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
                parsed_llm_response.full_response, config.model, full_message=True
            ),
            config.model,
            time_elapsed,
        )

        messages_snapshot.append(
            ChatCompletionAssistantMessageParam(
                role="assistant", content=parsed_llm_response.full_response
            )
        )
        self.add_model_message(parsed_llm_response.full_response, messages_snapshot)
        return parsed_llm_response.file_edits
