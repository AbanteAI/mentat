from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import List, Optional

from openai import RateLimitError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.llm_api_handler import (
    TOKEN_COUNT_WARNING,
    count_tokens,
    get_max_tokens,
    prompt_tokens,
)
from mentat.parsers.file_edit import FileEdit
from mentat.parsers.parser import ParsedLLMResponse
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import ModelMessage, TranscriptMessage, UserMessage
from mentat.utils import add_newline


class MentatAssistantMessageParam(ChatCompletionAssistantMessageParam):
    parsed_llm_response: ParsedLLMResponse


class Conversation:
    def __init__(self):
        self._messages = list[ChatCompletionMessageParam]()

        # This contains a list of messages used for transcripts
        self.literal_messages = list[TranscriptMessage]()

    async def display_token_count(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        code_context = session_context.code_context

        if "gpt-4" not in config.model:
            stream.send(
                "Warning: Mentat has only been tested on GPT-4. You may experience"
                " issues with quality. This model may not be able to respond in"
                " mentat's edit format.",
                style="warning",
            )
            if "gpt-3.5" not in config.model:
                stream.send(
                    "Warning: Mentat does not know how to calculate costs or context"
                    " size for this model.",
                    style="warning",
                )

        messages = self.get_messages()
        code_message = await code_context.get_code_message(
            prompt_tokens(
                messages,
                config.model,
            ),
            suppress_context_check=True,
        )
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=code_message,
            )
        )
        tokens = prompt_tokens(messages, config.model)

        context_size = get_max_tokens()
        if tokens + config.token_buffer > context_size:
            _plural = len(code_context.include_files) > 1
            _exceed = tokens > context_size
            message: dict[tuple[bool, bool], str] = {
                (False, False): " is close to",
                (False, True): " exceeds",
                (True, False): "s are close to",
                (True, True): "s exceed",
            }
            stream.send(
                f"Included file{message[(_plural, _exceed)]} token limit"
                f" ({tokens} / {context_size}).",
                style="warning",
            )
        else:
            stream.send(
                f"Prompt and included files token count: {tokens} / {context_size}",
                style="info",
            )

    # The transcript logger logs tuples containing the actual message sent by the user or LLM
    # and (for LLM messages) the LLM conversation that led to that LLM response
    def add_transcript_message(self, transcript_message: TranscriptMessage):
        transcript_logger = logging.getLogger("transcript")
        transcript_logger.info(json.dumps(transcript_message))
        self.literal_messages.append(transcript_message)

    def add_user_message(self, message: str, image: Optional[str] = None):
        """Used for actual user input messages"""
        content: List[ChatCompletionContentPartParam] | str = message
        if image:
            content = [
                {
                    "type": "text",
                    "text": message,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image,
                    },
                },
            ]
        self.add_transcript_message(UserMessage(message=content, prior_messages=None))
        self.add_message(ChatCompletionUserMessageParam(role="user", content=content))

    def add_model_message(
        self,
        message: str,
        messages_snapshot: list[ChatCompletionMessageParam],
        parsed_llm_response: ParsedLLMResponse,
    ):
        """Used for actual model output messages"""
        self.add_transcript_message(
            ModelMessage(message=message, prior_messages=messages_snapshot)
        )
        self.add_message(
            MentatAssistantMessageParam(
                parsed_llm_response=parsed_llm_response,
                role="assistant",
                content=message,
            )
        )

    def add_message(self, message: ChatCompletionMessageParam):
        """Used for adding messages to the models conversation. Does not add a left-side message to the transcript!"""
        self._messages.append(message)

    def get_messages(
        self,
        include_system_prompt: bool = True,
        include_parsed_llm_responses: bool = False,
    ) -> list[ChatCompletionMessageParam]:
        """Returns the messages in the conversation. The system message may change throughout
        the conversation and messages may contain additional metadata not supported by the API,
        so it is important to access the messages through this method.
        """
        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        _messages = [
            (  # Remove metadata from messages by default
                ChatCompletionAssistantMessageParam(
                    role=msg["role"], content=msg.get("content")
                )
                if msg["role"] == "assistant" and include_parsed_llm_responses is False
                else msg
            )
            for msg in self._messages.copy()
        ]

        if config.no_parser_prompt or not include_system_prompt:
            return _messages
        else:
            parser = config.parser
            prompt = parser.get_system_prompt()
            prompt_message: ChatCompletionMessageParam = (
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=prompt,
                )
            )
            return [prompt_message] + _messages

    def clear_messages(self) -> None:
        """Clears the messages in the conversation"""
        self._messages = list[ChatCompletionMessageParam]()

    async def _stream_model_response(
        self,
        messages: list[ChatCompletionMessageParam],
        loading_multiplier: float = 0.0,
    ) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager
        config = session_context.config
        parser = config.parser
        llm_api_handler = session_context.llm_api_handler
        cost_tracker = session_context.cost_tracker

        if loading_multiplier:
            stream.send(
                "Sending query and context to LLM",
                channel="loading",
                progress=50 * loading_multiplier,
            )
        response = await llm_api_handler.call_llm_api(
            messages,
            config.model,
            stream=True,
            response_format=parser.response_format(),
        )
        if loading_multiplier:
            stream.send(
                None,
                channel="loading",
                progress=50 * loading_multiplier,
                terminate=True,
            )

        num_prompt_tokens = prompt_tokens(messages, config.model)
        stream.send(f"Total token count: {num_prompt_tokens}", style="info")
        if num_prompt_tokens > TOKEN_COUNT_WARNING:
            stream.send(
                "Warning: LLM performance drops off rapidly at large context sizes. Use"
                " /clear to clear context or use /exclude to exclude any uneccessary"
                " files.",
                style="warning",
            )

        stream.send("Streaming... use control-c to interrupt the model at any point\n")
        async with parser.interrupt_catcher():
            parsed_llm_response = await parser.stream_and_parse_llm_response(
                add_newline(response)
            )
        # Sampler and History require previous_file_lines
        for file_edit in parsed_llm_response.file_edits:
            file_edit.previous_file_lines = code_file_manager.file_lines.get(
                file_edit.file_path, []
            )
        if not parsed_llm_response.interrupted:
            cost_tracker.display_last_api_call()
        else:
            # Generator doesn't log the api call if we interrupt it
            cost_tracker.log_api_call_stats(
                num_prompt_tokens,
                count_tokens(
                    parsed_llm_response.full_response, config.model, full_message=False
                ),
                config.model,
                display=True,
            )

        messages.append(
            ChatCompletionAssistantMessageParam(
                role="assistant", content=parsed_llm_response.full_response
            )
        )
        self.add_model_message(
            parsed_llm_response.full_response, messages, parsed_llm_response
        )

        return parsed_llm_response

    async def get_model_response(self) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        code_context = session_context.code_context

        messages_snapshot = self.get_messages()

        # Get current code message
        loading_multiplier = 1.0 if config.auto_context_tokens > 0 else 0.0
        prompt = messages_snapshot[-1].get("content")
        if isinstance(prompt, list):
            text_prompts = [
                p.get("text", "") for p in prompt if p.get("type") == "text"
            ]
            prompt = " ".join(text_prompts)
        code_message = await code_context.get_code_message(
            prompt_tokens(messages_snapshot, config.model),
            prompt=(
                prompt  # Prompt can be image as well as text
                if isinstance(prompt, str)
                else ""
            ),
            loading_multiplier=0.5 * loading_multiplier,
        )
        messages_snapshot.insert(
            0 if config.no_parser_prompt else 1,
            ChatCompletionSystemMessageParam(role="system", content=code_message),
        )

        try:
            response = await self._stream_model_response(
                messages_snapshot,
                loading_multiplier=0.5 * loading_multiplier,
            )
        except RateLimitError:
            stream.send(
                "Rate limit error received from OpenAI's servers using model"
                f' {config.model}.\nUse "/config model <model_name>" to switch to a'
                " different model.",
                style="error",
            )
            return ParsedLLMResponse("", "", list[FileEdit]())
        finally:
            if loading_multiplier:
                stream.send(None, channel="loading", terminate=True)
        return response

    def remaining_context(self) -> int | None:
        ctx = SESSION_CONTEXT.get()
        return get_max_tokens() - prompt_tokens(self.get_messages(), ctx.config.model)

    def can_add_to_context(self, message: str) -> bool:
        """
        Whether or not the model has enough context remaining to add this message.
        Will take token buffer into account and uses full_message=True.
        """
        ctx = SESSION_CONTEXT.get()

        remaining_context = self.remaining_context()
        return (
            remaining_context is not None
            and remaining_context
            - count_tokens(message, ctx.config.model, full_message=True)
            - ctx.config.token_buffer
            > 0
        )

    async def run_command(self, command: list[str]) -> bool:
        """
        Runs a command and, if there is room, adds the output to the conversation under the 'system' role.
        """
        ctx = SESSION_CONTEXT.get()

        ctx.stream.send("Running command: ", end="", style="info")
        ctx.stream.send(" ".join(command), style="warning")
        ctx.stream.send("Command output:", style="info")

        try:
            process = subprocess.Popen(
                command,
                cwd=ctx.cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output = list[str]()
            while True:
                if process.stdout is None:
                    break
                line = process.stdout.readline()
                if not line:
                    break
                output.append(line)
                ctx.stream.send(line, end="")
                # This gives control back to the asyncio event loop so we can actually print what we sent
                # Unfortunately asyncio.sleep(0) won't work https://stackoverflow.com/a/74505785
                # Note: if subprocess doesn't flush, output can't and won't be streamed.
                await asyncio.sleep(0.01)
        except FileNotFoundError:
            output = [f"Invalid command: {' '.join(command)}"]
            ctx.stream.send(output[0])
        output = "".join(output)
        message = f"Command ran:\n{' '.join(command)}\nCommand output:\n{output}"

        if self.can_add_to_context(message):
            self.add_message(
                ChatCompletionSystemMessageParam(role="system", content=message)
            )
            ctx.stream.send(
                "Successfully added command output to model context.", style="success"
            )
            return True
        else:
            ctx.stream.send(
                "Not enough tokens remaining in model's context to add command output"
                " to model context.",
                style="error",
            )
            return False

    def _get_user_message(self, message: ChatCompletionUserMessageParam) -> str:
        if not message["content"]:
            return ""
        elif isinstance(message["content"], str):
            return message["content"]
        else:
            full = ""
            for part in message["content"]:
                if part["type"] == "text":
                    full += part["text"]
            return full

    def amend(self) -> Optional[str]:
        for i, message in reversed(list(enumerate(self._messages))):
            if message["role"] == "user" and self._get_user_message(message):
                self._messages = self._messages[:i]
                return self._get_user_message(message)
