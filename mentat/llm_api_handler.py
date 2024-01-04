from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path
from timeit import default_timer
from typing import (
    Any,
    AsyncIterator,
    Callable,
    List,
    Literal,
    Optional,
    TypedDict,
    cast,
    overload,
)

import litellm
import sentry_sdk
import tiktoken
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    AsyncStream,
    AuthenticationError,
)
from openai.types import CreateEmbeddingResponse
from openai.types.audio import Transcription
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat
from PIL import Image

from mentat.errors import MentatError, ReturnToUser
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path

TOKEN_COUNT_WARNING = 32000


def is_test_environment():
    """Returns True if in pytest and not benchmarks"""
    benchmarks_running = os.getenv("MENTAT_BENCHMARKS_RUNNING")
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        and "--benchmark" not in sys.argv
        and (not bool(benchmarks_running) or benchmarks_running == "false")
    )


def api_guard(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that should be used on any function that calls an LLM API

    It does two things:
    1. Raises if the function is called in tests (that aren't benchmarks)
    2. Converts APIConnectionErrors to MentatErrors
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        assert (
            not is_test_environment()
        ), "OpenAI call attempted in non-benchmark test environment!"
        try:
            return await func(*args, **kwargs)
        except APIConnectionError:
            raise MentatError(
                "API connection error: please check your internet connection and try"
                " again."
            )

    return wrapper


# Ensures that each chunk will have at most one newline character
def chunk_to_lines(chunk: ChatCompletionChunk) -> list[str]:
    content = None
    if len(chunk.choices) > 0:
        content = chunk.choices[0].delta.content
    return ("" if content is None else content).splitlines(keepends=True)


class Model(TypedDict):
    max_tokens: int
    input_cost_per_token: float
    output_cost_per_token: float
    litellm_provider: str
    mode: str


def _get_model_info(model: str) -> Optional[Model]:
    try:
        return litellm.get_model_info(model)  # pyright: ignore
    except Exception:
        return None


def available_models() -> List[str]:
    return litellm.model_list  # pyright: ignore


def available_embedding_models() -> List[str]:
    return litellm.all_embedding_models  # pyright: ignore


def model_context_size(model: str) -> Optional[int]:
    model_info = _get_model_info(model)
    return model_info["max_tokens"] if model_info is not None else None


def model_price_per_1000_tokens(model: str) -> Optional[tuple[float, float]]:
    model_info = _get_model_info(model)
    return (
        (model_info["input_cost_per_token"], model_info["output_cost_per_token"])
        if model_info is not None
        else None
    )


def get_max_tokens() -> int:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    config = session_context.config

    context_size = model_context_size(config.model)
    maximum_context = config.maximum_context

    if context_size is not None and maximum_context is not None:
        return min(context_size, maximum_context)
    elif context_size is not None:
        return context_size
    elif maximum_context is not None:
        return maximum_context
    else:
        maximum_context = 4096
        # This attr has a converter from str to int
        config.maximum_context = str(maximum_context)
        stream.send(
            f"Context size for {config.model} is not known. Set maximum-context"
            " with `/config maximum_context <value>`. Using a default value of"
            f" {maximum_context}.",
            color="yellow",
        )
        return maximum_context


def is_context_sufficient(tokens: int) -> bool:
    ctx = SESSION_CONTEXT.get()

    max_tokens = get_max_tokens()
    if max_tokens - tokens < ctx.config.token_buffer:
        ctx.stream.send(
            f"The context size is limited to {max_tokens} tokens and your current"
            f" request uses {tokens} tokens. Please use `/exclude` to remove"
            " some files from context or `/clear` to reset the conversation",
            color="light_red",
        )
        return False

    return True


# litellm's token counting functions are inaccurate and don't count picture tokens;
# if we are using OpenAI, use our functions instead.
def _open_ai_count_tokens(message: str, model: str, full_message: bool) -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(message, disallowed_special=())) + (
        4 if full_message else 0
    )


def _open_ai_prompt_tokens(
    messages: List[ChatCompletionMessageParam], model: str
) -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    num_tokens = 0
    for message in messages:
        # every message follows <|start|>{role/name}\n{content}<|end|>\n
        # this has 5 tokens (start token, role, \n, end token, \n), but we count the role token later
        num_tokens += 4
        for key, value in message.items():
            if isinstance(value, list) and key == "content":
                value = cast(List[ChatCompletionContentPartParam], value)
                for entry in value:
                    if entry["type"] == "text":
                        num_tokens += len(encoding.encode(entry["text"]))
                    if entry["type"] == "image_url":
                        image_base64: str = entry["image_url"]["url"].split(",")[1]
                        image_bytes: bytes = base64.b64decode(image_base64)
                        image = Image.open(io.BytesIO(image_bytes))
                        size = image.size
                        # As described here: https://platform.openai.com/docs/guides/vision/calculating-costs
                        scale = min(1, 2048 / max(size))
                        size = (int(size[0] * scale), int(size[1] * scale))
                        scale = min(1, 768 / min(size))
                        size = (int(size[0] * scale), int(size[1] * scale))
                        num_tokens += 85 + 170 * ((size[0] + 511) // 512) * (
                            (size[1] + 511) // 512
                        )
            elif isinstance(value, str):
                num_tokens += len(encoding.encode(value))
            if key == "name":  # if there's a name, the role is omitted
                num_tokens -= 1  # role is always required and always 1 token
    num_tokens += 2  # every reply is primed with <|start|>assistant
    return num_tokens


def count_tokens(message: str, model: str, full_message: bool) -> int:
    """
    Calculates the tokens in this message. Will NOT be accurate for a full prompt!
    Use prompt_tokens to get the exact amount of tokens for a prompt.
    If full_message is true, will include the extra 4 tokens used in a chat completion by this message
    if this message is part of a prompt. You do NOT want full_message to be true for a response.
    """
    model_info = _get_model_info(model)
    if model_info is not None and model_info["litellm_provider"] == "openai":
        return _open_ai_count_tokens(message, model, full_message)
    else:
        return litellm.token_counter(model, text=message)  # pyright: ignore


def prompt_tokens(messages: List[ChatCompletionMessageParam], model: str) -> int:
    """
    Returns the number of tokens used by a prompt if it was sent to OpenAI for a chat completion.
    Adapted from https://platform.openai.com/docs/guides/text-generation/managing-tokens
    """
    model_info = _get_model_info(model)
    if model_info is not None and model_info["litellm_provider"] == "openai":
        return _open_ai_prompt_tokens(messages, model)
    else:
        return litellm.token_counter(model, messages=messages)  # pyright: ignore


class LlmApiHandler:
    """Used for any functions that require calling the external LLM API"""

    def load_env(self):
        ctx = SESSION_CONTEXT.get()

        if not load_dotenv(mentat_dir_path / ".env"):
            load_dotenv()

        key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        azure_key = os.getenv("AZURE_OPENAI_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

        # We don't have any use for a synchronous client, but if we ever do we can easily make it here
        if azure_endpoint and azure_key:
            self.async_client = AsyncAzureOpenAI(
                api_key=azure_key,
                api_version="2023-12-01-preview",
                azure_endpoint=azure_endpoint,
            )
        elif key:
            self.async_client = AsyncOpenAI(api_key=key, base_url=base_url)
        else:
            self.async_client = None

        if self.async_client is not None:
            try:
                self.async_client.models.list()  # Test the key
            except AuthenticationError as e:
                ctx.stream.send(f"OpenAI API gave Authentication Error:\n{e}")
                self.async_client = None

    @overload
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: Literal[True],
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> AsyncIterator[ChatCompletionChunk]: ...

    @overload
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: Literal[False],
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> ChatCompletion: ...

    @api_guard
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: bool,
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> ChatCompletion | AsyncIterator[ChatCompletionChunk]:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        cost_tracker = session_context.cost_tracker

        # Confirm that model has enough tokens remaining.
        tokens = prompt_tokens(messages, model)
        if not is_context_sufficient(tokens):
            raise ReturnToUser()

        start_time = default_timer()
        with sentry_sdk.start_span(description="LLM Call") as span:
            span.set_tag("model", model)

            try:
                # OpenAI's API is bugged; when gpt-4-vision-preview is used, including the response format
                # at all returns a 400 error.
                # Additionally, gpt-4-vision-preview has a max response of 30 tokens by default.
                # Until this is fixed, we have to use this workaround.
                if model == "gpt-4-vision-preview":
                    response = cast(
                        ChatCompletion | AsyncIterator[ChatCompletionChunk],
                        await litellm.acompletion(  # pyright: ignore
                            model=model,
                            messages=messages,
                            temperature=config.temperature,
                            stream=stream,
                            custom_llm_provider=config.llm_provider,
                            max_tokens=4096,
                        ),
                    )
                else:
                    response = cast(
                        ChatCompletion | AsyncIterator[ChatCompletionChunk],
                        await litellm.acompletion(  # pyright: ignore
                            model=model,
                            messages=messages,
                            temperature=config.temperature,
                            stream=stream,
                            custom_llm_provider=config.llm_provider,
                            response_format=response_format,  # pyright: ignore
                        ),
                    )
            except litellm.APIError as e:
                session_context.stream.send(f"Error accessing LLM: {e}", color="red")
                raise ReturnToUser()
            except litellm.NotFoundError:
                llm_provider_error_message = f" for llm_provider {config.llm_provider}"
                session_context.stream.send(
                    "Unknown model"
                    f" {model}{llm_provider_error_message if config.llm_provider is not None else ''}."
                    " Please use `/context model <model>` to switch models.",
                    color="red",
                )
                raise ReturnToUser()

        # We have to cast response since pyright isn't smart enough to connect
        # the dots between stream and the overloaded create function
        if not stream:
            time_elapsed = default_timer() - start_time
            response_tokens = count_tokens(
                cast(ChatCompletion, response).choices[0].message.content or "",
                model,
                full_message=False,
            )
            cost_tracker.log_api_call_stats(
                tokens, response_tokens, model, time_elapsed
            )
        else:
            cost_tracker.last_api_call = ""
            response = cost_tracker.response_logger_wrapper(
                tokens, cast(AsyncStream[ChatCompletionChunk], response), model
            )

        return response

    @api_guard
    async def call_embedding_api(
        self, input_texts: list[str], model: str = "text-embedding-ada-002"
    ) -> list[list[float]]:
        response = cast(
            CreateEmbeddingResponse,
            await litellm.aembedding(input=input_texts, model=model),  # pyright: ignore
        )
        return [embedding.embedding for embedding in response.data]

    @api_guard
    async def call_whisper_api(self, audio_path: Path) -> str:
        ctx = SESSION_CONTEXT.get()

        if self.async_client is None:
            ctx.stream.send(
                "You must provide a valid OpenAI API key to use the Whisper API."
            )
            raise ReturnToUser()
        audio_file = open(audio_path, "rb")
        transcript: Transcription = await self.async_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return transcript.text
