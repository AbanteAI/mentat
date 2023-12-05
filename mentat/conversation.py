from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from timeit import default_timer
from typing import TYPE_CHECKING, List, Optional

from openai import RateLimitError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.errors import MentatError
from mentat.llm_api_handler import count_tokens, model_context_size, prompt_tokens
from mentat.parsers.parser import ParsedLLMResponse
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import ModelMessage, TranscriptMessage, UserMessage
from mentat.utils import add_newline

if TYPE_CHECKING:
    from mentat.parsers.file_edit import FileEdit


class Conversation:
    def __init__(self):
        self._messages = list[ChatCompletionMessageParam]()

        # This contains a list of messages used for transcripts
        self.literal_messages = list[TranscriptMessage]()

    def _get_max_tokens(self) -> Optional[int]:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        context_size = model_context_size(config.model)
        maximum_context = config.maximum_context
        if maximum_context is not None:
            if context_size:
                return min(context_size, maximum_context)
            else:
                return maximum_context
        else:
            return context_size

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

        included_code_message = ["Code Files:"] + [
            line
            for features_for_path in code_context.include_files.values()
            for feature in features_for_path
            for line in feature.get_code_message()
        ]  # NOTE: missing diff info. negligible (0-30 tokens)
        messages = self.get_messages() + [
            ChatCompletionSystemMessageParam(
                role="system",
                content="\n".join(included_code_message),
            )
        ]
        tokens = prompt_tokens(
            messages,
            config.model,
        )

        context_size = self._get_max_tokens()
        if not context_size:
            raise MentatError(
                f"Context size for {config.model} is not known. Please set"
                " maximum-context with `/config maximum_context value`."
            )
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
                f" ({tokens} / {context_size}). Truncating based on task similarity.",
                color="yellow",
            )
        else:
            stream.send(
                f"Prompt and included files token count: {tokens} / {context_size}",
                color="cyan",
            )

    # The transcript logger logs tuples containing the actual message sent by the user or LLM
    # and (for LLM messages) the LLM conversation that led to that LLM response
    def add_transcript_message(self, transcript_message: TranscriptMessage):
        transcript_logger = logging.getLogger("transcript")
        transcript_logger.info(json.dumps(transcript_message))
        self.literal_messages.append(transcript_message)

    def add_user_message(self, message: str, image: Optional[str] = None):
        """Used for actual user input messages"""
        content: List[ChatCompletionContentPartParam] = [
            {
                "type": "text",
                "text": message,
            },
        ]
        if image:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image,
                    },
                },
            )
        self.add_transcript_message(UserMessage(message=content, prior_messages=None))
        self.add_message(ChatCompletionUserMessageParam(role="user", content=content))

    def add_model_message(
        self, message: str, messages_snapshot: list[ChatCompletionMessageParam]
    ):
        """Used for actual model output messages"""
        self.add_transcript_message(
            ModelMessage(message=message, prior_messages=messages_snapshot)
        )
        self.add_message(
            ChatCompletionAssistantMessageParam(role="assistant", content=message)
        )

    def add_message(self, message: ChatCompletionMessageParam):
        """Used for adding messages to the models conversation. Does not add a left-side message to the transcript!"""
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

        num_prompt_tokens = prompt_tokens(messages, config.model)
        context_size = model_context_size(config.model)
        if context_size:
            if num_prompt_tokens > context_size - config.token_buffer:
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

        stream.send(f"Total token count: {num_prompt_tokens}", color="cyan")
        stream.send("Streaming... use control-c to interrupt the model at any point\n")
        async with parser.interrupt_catcher():
            parsed_llm_response = await parser.stream_and_parse_llm_response(
                add_newline(response)
            )

        time_elapsed = default_timer() - start_time
        return (parsed_llm_response, time_elapsed, num_prompt_tokens)

    async def get_model_response(self) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        code_context = session_context.code_context
        cost_tracker = session_context.cost_tracker

        messages_snapshot = self.get_messages()

        # Rebuild code context with active code and available tokens
        tokens = prompt_tokens(messages_snapshot, config.model)

        loading_multiplier = 1.0 if config.auto_context else 0.0
        prompt = messages_snapshot[-1]["content"]
        if isinstance(prompt, list):
            text_prompts = [
                p.get("text", "") for p in prompt if p.get("type") == "text"
            ]
            prompt = " ".join(text_prompts)
        max_tokens = self._get_max_tokens()
        if max_tokens is None:
            stream.send(
                f"Context size for {config.model} is not known. Please set"
                " maximum-context with `/config maximum_context value`.",
                color="light_red",
            )
            return ParsedLLMResponse("", "", list[FileEdit]())

        if max_tokens - tokens < config.token_buffer:
            if max_tokens - tokens < 0:
                stream.send(
                    f"The context size is limited to {max_tokens} tokens and"
                    f" previous messages plus system prompts use {tokens} tokens."
                    " Please use `/clear` to reset or restart the session.",
                    color="light_red",
                )
            else:
                stream.send(
                    f"The context size is limited to {max_tokens} tokens and"
                    f" previous messages plus system prompts use {tokens} tokens,"
                    " leaving insufficent tokens for a response. Please use"
                    " `/clear` to reset or restart the session.",
                    color="light_red",
                )
            return ParsedLLMResponse("", "", list[FileEdit]())

        code_message = await code_context.get_code_message(
            (
                # Prompt can be image as well as text
                prompt
                if isinstance(prompt, str)
                else ""
            ),
            max_tokens - tokens - config.token_buffer,
            loading_multiplier=0.5 * loading_multiplier,
        )
        messages_snapshot.append(
            ChatCompletionSystemMessageParam(role="system", content=code_message)
        )

        # Doesn't seem to improve performance much
        # if agent_handler.agent_enabled:
        # agent_message = (
        #    "You are currently being run autonomously. After making your changes,"
        #    " you will have the chance to lint and test your code. If applicable,"
        #    " add tests that you can use to test your code."
        # )
        # messages_snapshot.append(
        #    ChatCompletionSystemMessageParam(role="system", content=agent_message)
        # )

        try:
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
            return ParsedLLMResponse("", "", list[FileEdit]())
        finally:
            if loading_multiplier:
                stream.send(None, channel="loading", terminate=True)

        cost_tracker.log_api_call_stats(
            num_prompt_tokens,
            count_tokens(
                parsed_llm_response.full_response, config.model, full_message=False
            ),
            config.model,
            time_elapsed,
            display=True,
        )

        messages_snapshot.append(
            ChatCompletionAssistantMessageParam(
                role="assistant", content=parsed_llm_response.full_response
            )
        )
        self.add_model_message(parsed_llm_response.full_response, messages_snapshot)
        return parsed_llm_response

    def remaining_context(self) -> int | None:
        ctx = SESSION_CONTEXT.get()
        max_context = self._get_max_tokens()
        if max_context is None:
            return None

        return max_context - prompt_tokens(self.get_messages(), ctx.config.model)

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

        ctx.stream.send(f"Running command: {' '.join(command)}", color="cyan")
        ctx.stream.send("Command output:", color="cyan")

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
                "Successfully added command output to model context.", color="cyan"
            )
            return True
        else:
            ctx.stream.send(
                "Not enough tokens remaining in model's context to add command output"
                " to model context.",
                color="light_red",
            )
            return False
