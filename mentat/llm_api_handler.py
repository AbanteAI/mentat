from __future__ import annotations

import os
import sys
from typing import Literal, Optional, overload

import sentry_sdk
import tiktoken
from dotenv import load_dotenv
from openai import AsyncOpenAI, AsyncStream, AuthenticationError
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
)

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


def count_tokens(message: str, model: str, full_message: bool = False) -> int:
    """
    Calculates the tokens in this message. Will NOT be accurate for a full conversation!
    Use conversation_tokens to get the exact amount of tokens in a conversation.
    If full_message is true, will include the extra 4 tokens used in a chat completion by this message.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(message, disallowed_special=())) + (
        4 if full_message else 0
    )


def conversation_tokens(messages: list[ChatCompletionMessageParam], model: str):
    """
    Returns the number of tokens used by a full conversation.
    Adapted from https://platform.openai.com/docs/guides/text-generation/managing-tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    num_tokens = 0
    for message in messages:
        # every message follows <im_start>{role/name}\n{content}<im_end>\n
        num_tokens += 4
        for key, value in message.items():
            if not isinstance(value, str):
                continue
            num_tokens += len(encoding.encode(value))
            if key == "name":  # if there's a name, the role is omitted
                num_tokens -= 1  # role is always required and always 1 token
    num_tokens += 2  # every reply is primed with <im_start>assistant
    return num_tokens


# TODO: These two functions should be a dictionary
def model_context_size(model: str) -> Optional[int]:
    if model == "gpt-4-1106-preview":
        return 128000
    elif "gpt-4" in model:
        if "32k" in model:
            return 32768
        else:
            return 8192
    elif "gpt-3.5" in model:
        if "16k" in model:
            return 16385
        else:
            return 4097
    elif "ada-002" in model:
        return 8191
    else:
        return None


def model_price_per_1000_tokens(model: str) -> Optional[tuple[float, float]]:
    """Returns (input, output) cost per 1000 tokens in USD"""
    if model == "gpt-4-1106-preview":
        return (0.01, 0.03)
    elif "gpt-4" in model:
        if "32k" in model:
            return (0.06, 0.12)
        else:
            return (0.03, 0.06)
    elif "gpt-3.5" in model:
        if "16k" in model:
            return (0.003, 0.004)
        else:
            return (0.0015, 0.002)
    elif "ada-002" in model:
        return (0.0001, 0)
    else:
        return None


class LlmApiHandler:
    """Used for any functions that require calling the external LLM API"""

    def initizalize_client(self):
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
    ) -> AsyncStream[ChatCompletionChunk]: ...

    @overload
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: Literal[False],
    ) -> ChatCompletion: ...

    async def call_llm_api(
        self, messages: list[ChatCompletionMessageParam], model: str, stream: bool
    ) -> ChatCompletion | AsyncStream[ChatCompletionChunk]:
        raise_if_in_test_environment()

        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        with sentry_sdk.start_span(description="LLM Call") as span:
            span.set_tag("model", model)
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config.temperature,
                stream=stream,
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
