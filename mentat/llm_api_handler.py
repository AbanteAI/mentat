from __future__ import annotations

import base64
import io
import os
import sys
from inspect import iscoroutinefunction
from pathlib import Path
from timeit import default_timer
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    cast,
    overload,
)

import attr
import sentry_sdk
import tiktoken
from chromadb.api.types import Embeddings
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    AsyncStream,
    AuthenticationError,
    AzureOpenAI,
    OpenAI,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat
from PIL import Image

from mentat.errors import MentatError, ReturnToUser, UserError
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
    """Decorator that should be used on any function that calls the OpenAI API

    It does two things:
    1. Raises if the function is called in tests (that aren't benchmarks)
    2. Converts APIConnectionErrors to MentatErrors
    """

    if iscoroutinefunction(func):

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            assert (
                not is_test_environment()
            ), "OpenAI call attempted in non-benchmark test environment!"
            try:
                return await func(*args, **kwargs)
            except APIConnectionError:
                raise MentatError(
                    "API connection error: please check your internet connection and"
                    " try again."
                )

        return async_wrapper
    else:

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            assert (
                not is_test_environment()
            ), "OpenAI call attempted in non-benchmark test environment!"
            try:
                return func(*args, **kwargs)
            except APIConnectionError:
                raise MentatError(
                    "API connection error: please check your internet connection and"
                    " try again."
                )

        return sync_wrapper


# Ensures that each chunk will have at most one newline character
def chunk_to_lines(chunk: ChatCompletionChunk) -> list[str]:
    content = None
    if len(chunk.choices) > 0:
        content = chunk.choices[0].delta.content
    return ("" if content is None else content).splitlines(keepends=True)


def get_encoding_for_model(model: str) -> tiktoken.Encoding:
    try:
        # OpenAI fine-tuned models are named `ft:<base model>:<name>:<id>`. If tiktoken
        # can't match the full string, it tries to match on startswith, e.g. 'gpt-4'
        _model = model.split(":")[1] if model.startswith("ft:") else model
        return tiktoken.encoding_for_model(_model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(message: str, model: str, full_message: bool) -> int:
    """
    Calculates the tokens in this message. Will NOT be accurate for a full prompt!
    Use prompt_tokens to get the exact amount of tokens for a prompt.
    If full_message is true, will include the extra 4 tokens used in a chat completion by this message
    if this message is part of a prompt. You do NOT want full_message to be true for a response.
    """
    encoding = get_encoding_for_model(model)
    return len(encoding.encode(message, disallowed_special=())) + (
        4 if full_message else 0
    )


def prompt_tokens(messages: list[ChatCompletionMessageParam], model: str):
    """
    Returns the number of tokens used by a prompt if it was sent to OpenAI for a chat completion.
    Adapted from https://platform.openai.com/docs/guides/text-generation/managing-tokens
    """
    encoding = get_encoding_for_model(model)

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


@attr.define
class Model:
    name: str = attr.field()
    context_size: int = attr.field()
    input_cost: float = attr.field()
    output_cost: float = attr.field()
    embedding_model: bool = attr.field(default=False)


class ModelsIndex(Dict[str, Model]):
    def __init__(self, models: Dict[str, Model]):
        super().update(models)

    def _validate_key(self, key: str) -> str:
        """Try to match fine-tuned models to their base models."""
        if not super().__contains__(key) and key.startswith("ft:"):
            base_model = key.split(":")[
                1
            ]  # e.g. "ft:gpt-3.5-turbo-1106:abante::8dsQMc4F"
            if super().__contains__(base_model):
                ctx = SESSION_CONTEXT.get()
                ctx.stream.send(
                    f"Using base model {base_model} for size and cost estimates.",
                    style="info",
                )
                super().__setitem__(
                    key, attr.evolve(super().__getitem__(base_model), name=key)
                )
                return key
        return key

    def __getitem__(self, key: str) -> Model:
        return super().__getitem__(self._validate_key(key))

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._validate_key(str(key)))


known_models = ModelsIndex(
    {
        "gpt-4-1106-preview": Model("gpt-4-1106-preview", 128000, 0.01, 0.03),
        "gpt-4-vision-preview": Model("gpt-4-vision-preview", 128000, 0.01, 0.03),
        "gpt-4": Model("gpt-4", 8192, 0.03, 0.06),
        "gpt-4-32k": Model("gpt-4-32k", 32768, 0.06, 0.12),
        "gpt-4-0613": Model("gpt-4-0613", 8192, 0.03, 0.06),
        "gpt-4-32k-0613": Model("gpt-4-32k-0613", 32768, 0.06, 0.12),
        "gpt-4-0314": Model("gpt-4-0314", 8192, 0.03, 0.06),
        "gpt-4-32k-0314": Model("gpt-4-32k-0314", 32768, 0.06, 0.12),
        "gpt-3.5-turbo-1106": Model("gpt-3.5-turbo-1106", 16385, 0.001, 0.002),
        "gpt-3.5-turbo": Model("gpt-3.5-turbo", 16385, 0.001, 0.002),
        "gpt-3.5-turbo-0613": Model("gpt-3.5-turbo-0613", 4096, 0.0015, 0.002),
        "gpt-3.5-turbo-16k-0613": Model("gpt-3.5-turbo-16k-0613", 16385, 0.003, 0.004),
        "gpt-3.5-turbo-0301": Model("gpt-3.5-turbo-0301", 4096, 0.0015, 0.002),
        "text-embedding-ada-002": Model(
            "text-embedding-ada-002", 8191, 0.0001, 0, embedding_model=True
        ),
    }
)


def model_context_size(model: str) -> Optional[int]:
    if model not in known_models:
        return None
    else:
        return known_models[model].context_size


def model_price_per_1000_tokens(model: str) -> Optional[tuple[float, float]]:
    """Returns (input, output) cost per 1000 tokens in USD"""
    if model not in known_models:
        return None
    else:
        return known_models[model].input_cost, known_models[model].output_cost


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

    def initialize_client(self):
        ctx = SESSION_CONTEXT.get()

        if not load_dotenv(mentat_dir_path / ".env"):
            load_dotenv()
        key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        azure_key = os.getenv("AZURE_OPENAI_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

        # ChromaDB requires a sync function for embeddings
        if azure_endpoint and azure_key:
            ctx.stream.send("Using Azure OpenAI client.", style="warning")
            self.async_client = AsyncAzureOpenAI(
                api_key=azure_key,
                api_version="2023-12-01-preview",
                azure_endpoint=azure_endpoint,
            )
            self.sync_client = AzureOpenAI(
                api_key=azure_key,
                api_version="2023-12-01-preview",
                azure_endpoint=azure_endpoint,
            )
        else:
            if not key:
                if not base_url:
                    raise UserError(
                        "No OpenAI api key detected.\nEither place your key into a .env"
                        " file or export it as an environment variable."
                    )
                # If they set the base_url but not the key, they probably don't need a key, but the client requires one
                key = "fake_key"
            self.async_client = AsyncOpenAI(api_key=key, base_url=base_url)
            self.sync_client = OpenAI(api_key=key, base_url=base_url)

        try:
            self.async_client.models.list()  # Test the key
        except AuthenticationError as e:
            raise UserError(f"API gave an Authentication Error:\n{e}")

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
        raise_if_context_exceeds_max(tokens)

        start_time = default_timer()
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
                # This makes it slightly easier when using the litellm proxy or models outside of OpenAI
                if response_format["type"] == "text":
                    response = await self.async_client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=config.temperature,
                        stream=stream,
                    )
                else:
                    response = await self.async_client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=config.temperature,
                        stream=stream,
                        response_format=response_format,
                    )

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
    def call_embedding_api(
        self, input_texts: list[str], model: str = "text-embedding-ada-002"
    ) -> Embeddings:
        embeddings = self.sync_client.embeddings.create(
            input=input_texts, model=model
        ).data
        sorted_embeddings = sorted(embeddings, key=lambda e: e.index)
        return [result.embedding for result in sorted_embeddings]

    @api_guard
    async def call_whisper_api(self, audio_path: Path) -> str:
        audio_file = open(audio_path, "rb")
        transcript = await self.async_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return transcript.text
