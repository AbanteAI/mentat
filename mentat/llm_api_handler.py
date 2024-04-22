from __future__ import annotations

import logging
import os
import sys
from inspect import iscoroutinefunction
from pathlib import Path
from typing import (
    Any,
    Callable,
    List,
    Literal,
    Optional,
    TypeVar,
    overload,
)

import sentry_sdk
from dotenv import load_dotenv
from openai.types.chat.completion_create_params import ResponseFormat
from spice import EmbeddingResponse, Spice, SpiceMessage, SpiceResponse, StreamingSpiceResponse, TranscriptionResponse
from spice.errors import APIConnectionError, AuthenticationError, InvalidProviderError, NoAPIKeyError
from spice.models import WHISPER_1
from spice.providers import OPEN_AI
from spice.spice import UnknownModelError, get_model_from_name, get_provider_from_name

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


RetType = TypeVar("RetType")


def api_guard(func: Callable[..., RetType]) -> Callable[..., RetType]:
    """Decorator that should be used on any function that calls the OpenAI API

    It does two things:
    1. Raises if the function is called in tests (that aren't benchmarks)
    2. Converts APIConnectionErrors to MentatErrors
    """

    if iscoroutinefunction(func):

        async def async_wrapper(*args: Any, **kwargs: Any) -> RetType:
            assert not is_test_environment(), "OpenAI call attempted in non-benchmark test environment!"
            try:
                return await func(*args, **kwargs)
            except AuthenticationError:
                raise MentatError("Authentication error: Check your api key and try again.")
            except APIConnectionError:
                raise MentatError("API connection error: Check your internet connection and try again.")
            except UnknownModelError:
                SESSION_CONTEXT.get().stream.send(
                    "Unknown model. Use /config provider <provider> and try again.", style="error"
                )
                raise ReturnToUser()
            except InvalidProviderError:
                SESSION_CONTEXT.get().stream.send(
                    "Unknown provider. Use /config provider <provider> and try again.", style="error"
                )
                raise ReturnToUser()

        return async_wrapper  # pyright: ignore[reportReturnType]
    else:

        def sync_wrapper(*args: Any, **kwargs: Any) -> RetType:
            assert not is_test_environment(), "OpenAI call attempted in non-benchmark test environment!"
            try:
                return func(*args, **kwargs)
            except AuthenticationError:
                raise MentatError("Authentication error: Check your api key and try again.")
            except APIConnectionError:
                raise MentatError("API connection error: Check your internet connection and try again.")
            except UnknownModelError:
                SESSION_CONTEXT.get().stream.send(
                    "Unknown model. Use /config provider <provider> and try again.", style="error"
                )
                raise ReturnToUser()
            except InvalidProviderError:
                SESSION_CONTEXT.get().stream.send(
                    "Unknown provider. Use /config provider <provider> and try again.", style="error"
                )
                raise ReturnToUser()

        return sync_wrapper


# Ensures that each chunk will have at most one newline character
def chunk_to_lines(content: str) -> list[str]:
    return content.splitlines(keepends=True)


def get_max_tokens() -> int:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    config = session_context.config

    context_size = get_model_from_name(config.model).context_length
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
            style="error",
        )
        return maximum_context


def raise_if_context_exceeds_max(tokens: int):
    ctx = SESSION_CONTEXT.get()

    max_tokens = get_max_tokens()
    if max_tokens - tokens < ctx.config.token_buffer:
        ctx.stream.send(
            f"The context size is limited to {max_tokens} tokens and your current"
            f" request uses {tokens} tokens. Please use `/exclude` to remove"
            " some files from context or `/clear` to reset the conversation",
            style="error",
        )
        raise ReturnToUser()


class LlmApiHandler:
    """Used for any functions that require calling the external LLM API"""

    def __init__(self):
        self.spice = Spice()

    async def initialize_client(self):
        ctx = SESSION_CONTEXT.get()

        if not load_dotenv(mentat_dir_path / ".env") and not load_dotenv(ctx.cwd / ".env"):
            load_dotenv()

        user_provider = get_model_from_name(ctx.config.model).provider
        if ctx.config.provider is not None:
            try:
                user_provider = get_provider_from_name(ctx.config.provider)
            except InvalidProviderError:
                ctx.stream.send(
                    f"Unknown provider {ctx.config.provider}. Use /config provider <provider> to set your provider.",
                    style="warning",
                )
        elif user_provider is None:
            ctx.stream.send(
                f"Unknown model {ctx.config.model}. Use /config provider <provider> to set your provider.",
                style="warning",
            )

        # ragdaemon always needs an openai provider
        providers = [OPEN_AI]
        if user_provider is not None:
            providers.append(user_provider)

        for provider in providers:
            try:
                self.spice.load_provider(provider)
            except NoAPIKeyError:
                from mentat.session_input import collect_user_input

                match provider.name:
                    case "open_ai" | "openai":
                        env_variable = "OPENAI_API_KEY"
                    case "anthropic":
                        env_variable = "ANTHROPIC_API_KEY"
                    case "azure":
                        if os.getenv("AZURE_OPENAI_ENDPOINT") is None:
                            ctx.stream.send(
                                f"No Azure OpenAI endpoint detected. To avoid entering your endpoint on startup, create a .env file in"
                                " ~/.mentat/.env or in your workspace root and set AZURE_OPENAI_ENDPOINT.",
                                style="warning",
                            )
                            ctx.stream.send("Enter your endpoint:", style="info")
                            endpoint = (await collect_user_input(log_input=False)).data
                            os.environ["AZURE_OPENAI_ENDPOINT"] = endpoint
                        if os.getenv("AZURE_OPENAI_KEY") is not None:
                            return
                        env_variable = "AZURE_OPENAI_KEY"
                    case _:
                        raise MentatError(
                            f"No api key detected for provider {provider.name}. Create a .env file in ~/.mentat/.env or in your workspace root with your api key"
                        )

                ctx.stream.send(
                    f"No {provider.name} api key detected. To avoid entering your api key on startup, create a .env file in"
                    " ~/.mentat/.env or in your workspace root.",
                    style="warning",
                )
                ctx.stream.send("Enter your api key:", style="info")
                key = (await collect_user_input(log_input=False)).data
                os.environ[env_variable] = key

    @overload
    async def call_llm_api(
        self,
        messages: List[SpiceMessage],
        model: str,
        provider: Optional[str],
        stream: Literal[False],
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> SpiceResponse:
        ...

    @overload
    async def call_llm_api(
        self,
        messages: List[SpiceMessage],
        model: str,
        provider: Optional[str],
        stream: Literal[True],
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> StreamingSpiceResponse:
        ...

    @api_guard
    async def call_llm_api(
        self,
        messages: List[SpiceMessage],
        model: str,
        provider: Optional[str],
        stream: bool,
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> SpiceResponse | StreamingSpiceResponse:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        # Confirm that model has enough tokens remaining
        tokens = self.spice.count_prompt_tokens(messages, model, provider)
        raise_if_context_exceeds_max(tokens)

        with sentry_sdk.start_span(description="LLM Call") as span:
            span.set_tag("model", model)

            if not stream:
                response = await self.spice.get_response(
                    model=model,
                    provider=provider,
                    messages=messages,
                    temperature=config.temperature,
                    response_format=response_format,
                )
            else:
                response = await self.spice.stream_response(
                    model=model,
                    provider=provider,
                    messages=messages,
                    temperature=config.temperature,
                    response_format=response_format,
                )

        return response

    @api_guard
    def call_embedding_api(self, input_texts: list[str], model: str = "text-embedding-3-large") -> EmbeddingResponse:
        ctx = SESSION_CONTEXT.get()
        return self.spice.get_embeddings_sync(input_texts, model, provider=ctx.config.embedding_provider)

    @api_guard
    async def call_whisper_api(self, audio_path: Path) -> TranscriptionResponse:
        return await self.spice.get_transcription(audio_path, model=WHISPER_1)

    def display_cost_stats(self, response: SpiceResponse):
        ctx = SESSION_CONTEXT.get()

        display = f"Speed: {response.characters_per_second:.2f} char/s"
        if response.cost is not None:
            display += f" | Cost: ${response.cost / 100:.2f}"

        costs_logger = logging.getLogger("costs")
        costs_logger.info(display)

        ctx.stream.send(display, style="info")
