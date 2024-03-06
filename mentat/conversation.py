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
    raise_if_context_exceeds_max,
)
from mentat.parsers.file_edit import FileEdit
from mentat.parsers.parser import ParsedLLMResponse
from mentat.session_context import SESSION_CONTEXT
from mentat.stream_model_response import (
    get_two_step_system_prompt,
    stream_model_response,
    stream_model_response_two_step,
)
from mentat.transcripts import ModelMessage, TranscriptMessage, UserMessage


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

        tokens = await self.count_tokens(include_code_message=True)

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

    async def count_tokens(
        self,
        system_prompt: Optional[list[ChatCompletionMessageParam]] = None,
        include_code_message: bool = False,
    ) -> int:
        _messages = await self.get_messages(
            system_prompt=system_prompt, include_code_message=include_code_message
        )
        model = SESSION_CONTEXT.get().config.model
        return prompt_tokens(_messages, model)

    async def get_messages(
        self,
        system_prompt: Optional[list[ChatCompletionMessageParam]] = None,
        include_parsed_llm_responses: bool = False,
        include_code_message: bool = False,
    ) -> list[ChatCompletionMessageParam]:
        """Returns the messages in the conversation. The system message may change throughout
        the conversation and messages may contain additional metadata not supported by the API,
        so it is important to access the messages through this method.
        """
        ctx = SESSION_CONTEXT.get()

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

        if len(_messages) > 0 and _messages[-1].get("role") == "user":
            prompt = _messages[-1].get("content")
            if isinstance(prompt, list):
                text_prompts = [
                    p.get("text", "") for p in prompt if p.get("type") == "text"
                ]
                prompt = " ".join(text_prompts)
        else:
            prompt = ""

        if include_code_message:
            code_message = await ctx.code_context.get_code_message(
                prompt_tokens(_messages, ctx.config.model),
                prompt=(
                    prompt  # Prompt can be image as well as text
                    if isinstance(prompt, str)
                    else ""
                ),
            )
            _messages = [
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=code_message,
                )
            ] + _messages

        if system_prompt is None:
            if ctx.config.no_parser_prompt:
                system_prompt = []
            else:
                if ctx.config.two_step_edits:
                    system_prompt = [
                        ChatCompletionSystemMessageParam(
                            role="system",
                            content=get_two_step_system_prompt(),
                        )
                    ]
                else:
                    parser = ctx.config.parser
                    system_prompt = [
                        ChatCompletionSystemMessageParam(
                            role="system",
                            content=parser.get_system_prompt(),
                        )
                    ]

        return system_prompt + _messages

    def clear_messages(self) -> None:
        """Clears the messages in the conversation"""
        self._messages = list[ChatCompletionMessageParam]()

    async def get_model_response(self) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config

        messages_snapshot = await self.get_messages(include_code_message=True)
        tokens_used = prompt_tokens(messages_snapshot, config.model)
        raise_if_context_exceeds_max(tokens_used)

        try:
            if session_context.config.two_step_edits:
                response = await stream_model_response_two_step(messages_snapshot)
            else:
                response = await stream_model_response(messages_snapshot)
        except RateLimitError:
            stream.send(
                "Rate limit error received from OpenAI's servers using model"
                f' {config.model}.\nUse "/config model <model_name>" to switch to a'
                " different model.",
                style="error",
            )
            return ParsedLLMResponse("", "", list[FileEdit]())

        messages_snapshot.append(
            ChatCompletionAssistantMessageParam(
                role="assistant", content=response.full_response
            )
        )
        self.add_model_message(response.full_response, messages_snapshot, response)

        return response

    async def remaining_context(self) -> int | None:
        ctx = SESSION_CONTEXT.get()
        return get_max_tokens() - prompt_tokens(
            await self.get_messages(), ctx.config.model
        )

    async def can_add_to_context(self, message: str) -> bool:
        """
        Whether or not the model has enough context remaining to add this message.
        Will take token buffer into account and uses full_message=True.
        """
        ctx = SESSION_CONTEXT.get()

        remaining_context = await self.remaining_context()
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

        if await self.can_add_to_context(message):
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
