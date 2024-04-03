from __future__ import annotations

import base64
import io
import os
import sys
from inspect import iscoroutinefunction
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    cast,
)

import attr
import sentry_sdk
import tiktoken
from dotenv import load_dotenv
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat
from PIL import Image
from spice import APIConnectionError, Spice, SpiceEmbeddings, SpiceError, SpiceResponse, SpiceWhisper

from mentat.errors import MentatError, ReturnToUser
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path

TOKEN_COUNT_WARNING = 32000

if TYPE_CHECKING:
    # This import is slow
    from chromadb.api.types import Embeddings


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
            assert not is_test_environment(), "OpenAI call attempted in non-benchmark test environment!"
            try:
                return await func(*args, **kwargs)
            except APIConnectionError:
                raise MentatError("API connection error: please check your internet connection and" " try again.")
            except SpiceError as e:
                raise MentatError(f"API error: {e}")

        return async_wrapper
    else:

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            assert not is_test_environment(), "OpenAI call attempted in non-benchmark test environment!"
            try:
                return func(*args, **kwargs)
            except APIConnectionError:
                raise MentatError("API connection error: please check your internet connection and" " try again.")
            except SpiceError as e:
                raise MentatError(f"API error: {e}")

        return sync_wrapper


# Ensures that each chunk will have at most one newline character
def chunk_to_lines(content: str) -> list[str]:
    return content.splitlines(keepends=True)


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
    return len(encoding.encode(message, disallowed_special=())) + (4 if full_message else 0)


def normalize_messages_for_anthropic(
    messages: list[ChatCompletionMessageParam],
) -> list[ChatCompletionMessageParam]:
    """Claude expects the chat to start with at most one system message and afterwards user and system messages to
    alternate. This method consolidates all the system messages at the beginning of the conversation into one system
    message delimited by "\n"+"-"*80+"\n and turns future system messages into user messages annotated with "System:"
    and combines adjacent assistant or user messages into one assistant or user message.
    """
    replace_non_leading_systems = list[ChatCompletionMessageParam]()
    for i, message in enumerate(messages):
        if message["role"] == "system":
            if i == 0 or messages[i - 1]["role"] == "system":
                replace_non_leading_systems.append(message)
            else:
                content = "SYSTEM: " + (message["content"] or "")
                replace_non_leading_systems.append(ChatCompletionUserMessageParam(role="user", content=content))
        else:
            replace_non_leading_systems.append(message)

    concatenate_adjacent = list[ChatCompletionMessageParam]()
    current_role: str = ""
    current_content: str = ""
    delimiter = "\n" + "-" * 80 + "\n"
    for message in replace_non_leading_systems:
        if message["role"] == current_role:
            current_content += delimiter + str(message["content"])
        else:
            if current_role == "user":
                concatenate_adjacent.append(ChatCompletionUserMessageParam(role=current_role, content=current_content))
            elif current_role == "system":
                concatenate_adjacent.append(
                    ChatCompletionSystemMessageParam(role=current_role, content=current_content)
                )
            elif current_role == "assistant":
                concatenate_adjacent.append(
                    ChatCompletionAssistantMessageParam(role=current_role, content=current_content)
                )
            current_role = message["role"]
            current_content = str(message["content"])

    if current_role == "user":
        concatenate_adjacent.append(ChatCompletionUserMessageParam(role=current_role, content=current_content))
    elif current_role == "system":
        concatenate_adjacent.append(ChatCompletionSystemMessageParam(role=current_role, content=current_content))
    elif current_role == "assistant":
        concatenate_adjacent.append(ChatCompletionAssistantMessageParam(role=current_role, content=current_content))

    return concatenate_adjacent


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
                        num_tokens += 85 + 170 * ((size[0] + 511) // 512) * ((size[1] + 511) // 512)
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
            base_model = key.split(":")[1]  # e.g. "ft:gpt-3.5-turbo-1106:abante::8dsQMc4F"
            if super().__contains__(base_model):
                ctx = SESSION_CONTEXT.get()
                ctx.stream.send(
                    f"Using base model {base_model} for size and cost estimates.",
                    style="info",
                )
                super().__setitem__(key, attr.evolve(super().__getitem__(base_model), name=key))
                return key
        return key

    def __getitem__(self, key: str) -> Model:
        return super().__getitem__(self._validate_key(key))

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._validate_key(str(key)))


known_models = ModelsIndex(
    {
        "gpt-4-0125-preview": Model("gpt-4-0125-preview", 128000, 0.01, 0.03),
        "gpt-4-1106-preview": Model("gpt-4-1106-preview", 128000, 0.01, 0.03),
        "gpt-4-vision-preview": Model("gpt-4-vision-preview", 128000, 0.01, 0.03),
        "gpt-4": Model("gpt-4", 8192, 0.03, 0.06),
        "gpt-4-32k": Model("gpt-4-32k", 32768, 0.06, 0.12),
        "gpt-4-0613": Model("gpt-4-0613", 8192, 0.03, 0.06),
        "gpt-4-32k-0613": Model("gpt-4-32k-0613", 32768, 0.06, 0.12),
        "gpt-4-0314": Model("gpt-4-0314", 8192, 0.03, 0.06),
        "gpt-4-32k-0314": Model("gpt-4-32k-0314", 32768, 0.06, 0.12),
        "gpt-3.5-turbo-0125": Model("gpt-3.5-turbo-0125", 16385, 0.0005, 0.0015),
        "gpt-3.5-turbo-1106": Model("gpt-3.5-turbo-1106", 16385, 0.001, 0.002),
        "gpt-3.5-turbo": Model("gpt-3.5-turbo", 16385, 0.001, 0.002),
        "gpt-3.5-turbo-0613": Model("gpt-3.5-turbo-0613", 4096, 0.0015, 0.002),
        "gpt-3.5-turbo-16k-0613": Model("gpt-3.5-turbo-16k-0613", 16385, 0.003, 0.004),
        "gpt-3.5-turbo-0301": Model("gpt-3.5-turbo-0301", 4096, 0.0015, 0.002),
        "text-embedding-ada-002": Model("text-embedding-ada-002", 8191, 0.0001, 0, embedding_model=True),
        "claude-3-opus-20240229": Model("claude-3-opus-20240229", 200000, 0.015, 0.075),
        "claude-3-sonnet-20240229": Model("claude-3-sonnet-20240229", 200000, 0.003, 0.015),
        "claude-3-haiku-20240307": Model("claude-3-haiku-20240307", 200000, 0.00025, 0.00125),
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

    async def initialize_client(self):
        ctx = SESSION_CONTEXT.get()

        if not load_dotenv(mentat_dir_path / ".env") and not load_dotenv(ctx.cwd / ".env"):
            load_dotenv()

        if os.getenv("AZURE_OPENAI_KEY") is not None:
            embedding_and_whisper_provider = "azure"
        else:
            embedding_and_whisper_provider = "openai"

        self.spice_client = Spice()
        self.spice_embedding_client = SpiceEmbeddings(provider=embedding_and_whisper_provider)
        self.spice_whisper_client = SpiceWhisper(provider=embedding_and_whisper_provider)

    @api_guard
    async def call_llm_api(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str,
        stream: bool,
        response_format: ResponseFormat = ResponseFormat(type="text"),
    ) -> SpiceResponse:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        cost_tracker = session_context.cost_tracker

        if "claude" in config.model:
            messages = normalize_messages_for_anthropic(messages)

        # Confirm that model has enough tokens remaining.
        tokens = prompt_tokens(messages, model)
        raise_if_context_exceeds_max(tokens)

        # TODO: make spice message format and use across codebase consistently
        _messages = [
            {"role": cast(str, message["role"]), "content": cast(str, message["content"])} for message in messages
        ]
        if "type" in response_format and response_format["type"] == "json_object":
            _response_format = {"type": "json_object"}
        else:
            _response_format = {"type": "text"}

        with sentry_sdk.start_span(description="LLM Call") as span:
            span.set_tag("model", model)

            response = await self.spice_client.call_llm(
                model=model,
                messages=_messages,
                stream=stream,
                temperature=config.temperature,
                response_format=_response_format,
                logging_callback=cost_tracker.log_api_call_stats,
            )

        return response

    @api_guard
    def call_embedding_api(self, input_texts: list[str], model: str = "text-embedding-ada-002") -> Embeddings:
        return self.spice_embedding_client.get_embeddings(input_texts, model)

    @api_guard
    async def call_whisper_api(self, audio_path: Path) -> str:
        return await self.spice_whisper_client.get_whisper_transcription(audio_path)
