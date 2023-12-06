from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path
from typing import List, Literal, Optional, cast, overload

import sentry_sdk
import tiktoken
from dotenv import load_dotenv
from openai import AsyncOpenAI, AsyncStream, AuthenticationError
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat
from PIL import Image

from mentat.errors import UserError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path


def is_test_environment():
    """Returns True if in pytest and not benchmarks"""
    benchmarks_running = os.getenv("MENTAT_BENCHMARKS_RUNNING")
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        and "--benchmark" not in sys.argv
        and (not bool(benchmarks_running) or benchmarks_running == "false")
    )


def raise_if_in_test_environment():
    assert (
        not is_test_environment()
    ), "OpenAI call attempted in non benchmark test environment!"


# Ensures that each chunk will have at most one newline character
def chunk_to_lines(chunk: ChatCompletionChunk) -> list[str]:
    content = chunk.choices[0].delta.content
    return ("" if content is None else content).splitlines(keepends=True)


def count_tokens(message: str, model: str, full_message: bool) -> int:
    """
    Calculates the tokens in this message. Will NOT be accurate for a full prompt!
    Use prompt_tokens to get the exact amount of tokens for a prompt.
    If full_message is true, will include the extra 4 tokens used in a chat completion by this message
    if this message is part of a prompt. You do NOT want full_message to be true for a response.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(message, disallowed_special=())) + (
        4 if full_message else 0
    )


def prompt_tokens(messages: list[ChatCompletionMessageParam], model: str):
    """
    Returns the number of tokens used by a prompt if it was sent to OpenAI for a chat completion.
    Adapted from https://platform.openai.com/docs/guides/text-generation/managing-tokens
    """
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


def model_context_size(model: str) -> Optional[int]:
    context_sizes = {
        "gpt-4-1106-preview": 128000,
        "gpt-4-vision-preview": 128000,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-0613": 8192,
        "gpt-4-32k-0613": 32768,
        "gpt-4-0314": 8192,
        "gpt-4-32k-0314": 32768,
        "gpt-3.5-turbo-1106": 16385,
        "gpt-3.5-turbo": 16385,
        "gpt-3.5-turbo-0613": 4096,
        "gpt-3.5-turbo-16k-0613": 16385,
        "gpt-3.5-turbo-0301": 4096,
        "text-embedding-ada-002": 8191,
    }
    return context_sizes.get(model, None)


def model_price_per_1000_tokens(model: str) -> Optional[tuple[float, float]]:
    """Returns (input, output) cost per 1000 tokens in USD"""
    prices = {
        "gpt-4-1106-preview": (0.01, 0.03),
        "gpt-4-vision-preview": (0.01, 0.03),
        "gpt-4": (0.03, 0.06),
        "gpt-4-32k": (0.06, 0.12),
        "gpt-4-0613": (0.03, 0.06),
        "gpt-4-32k-0613": (0.06, 0.12),
        "gpt-4-0314": (0.03, 0.06),
        "gpt-4-32k-0314": (0.06, 0.12),
        "gpt-3.5-turbo-1106": (0.001, 0.002),
        "gpt-3.5-turbo": (0.001, 0.002),
        "gpt-3.5-turbo-0613": (0.0015, 0.002),
        "gpt-3.5-turbo-16k-0613": (0.003, 0.004),
        "gpt-3.5-turbo-0301": (0.0015, 0.002),
        "text-embedding-ada-002": (0.0001, 0),
    }
    return prices.get(model, None)


class LlmApiHandler:
    """Used for any functions that require calling the external LLM API"""

    def initialize_client(self):
        if not load_dotenv(mentat_dir_path / ".env"):
            load_dotenv()
        key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        if not key:
            raise UserError(
                "No OpenAI api key detected.\nEither place your key into a .env"
                " file or export it as an environment variable."
            )

        # We don't have any use for a synchronous client, but if we ever do we can easily make it here
        self.async_client = AsyncOpenAI(api_key=key, base_url=base_url)
        try:
            self.async_client.api_key = key
            self.async_client.models.list()  # Test the key
        except AuthenticationError as e:
            raise UserError(f"OpenAI gave an Authentication Error:\n{e}")

    @overload
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: Literal[True],
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> AsyncStream[ChatCompletionChunk]: ...

    @overload
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: Literal[False],
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> ChatCompletion: ...

    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: bool,
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> ChatCompletion | AsyncStream[ChatCompletionChunk]:
        raise_if_in_test_environment()

        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        with sentry_sdk.start_span(description="LLM Call") as span:
            span.set_tag("model", model)
            # OpenAI's API is bugged; when gpt-4-vision-preview is used, including the response format
            # at all returns a 400 error. Additionally, gpt-4-vision-preview has a max response of 30 tokens by default.
            # Until this is fixed, we have to use this workaround.
            if model == "gpt-4-vision-preview":
                response = await self.async_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=config.temperature,
                    stream=stream,
                    max_tokens=4096,
                )
            else:
                response = await self.async_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=config.temperature,
                    stream=stream,
                    response_format=response_format,
                )

        return response

    async def call_embedding_api(
        self, input_texts: list[str], model: str = "text-embedding-ada-002"
    ) -> list[list[float]]:
        raise_if_in_test_environment()

        response = await self.async_client.embeddings.create(
            input=input_texts, model=model
        )
        return [embedding.embedding for embedding in response.data]

    async def is_model_available(self, model: str) -> bool:
        raise_if_in_test_environment()

        available_models: list[str] = [
            model.id async for model in self.async_client.models.list()
        ]
        return model in available_models

    async def call_whisper_api(self, audio_path: Path) -> str:
        raise_if_in_test_environment()

        audio_file = open(audio_path, "rb")
        transcript = await self.async_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return transcript.text
