from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from functools import partial
from typing import Any, AsyncGenerator, Optional, cast

import backoff
import openai
import openai.error
import tiktoken
from backoff.types import Details
from dotenv import load_dotenv
from openai.error import AuthenticationError, RateLimitError, Timeout

from mentat.errors import MentatError, UserError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path

package_name = __name__.split(".")[0]

# openai doesn't seem to use type hints, so we have to use type: ignore and cast everywhere


# Check for .env file or already exported API key
# If no api key found, raise an error
def setup_api_key():
    if not load_dotenv(mentat_dir_path / ".env"):
        load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE")
    if base_url:
        openai.api_base = base_url
    if not key:
        raise UserError(
            "No OpenAI api key detected.\nEither place your key into a .env"
            " file or export it as an environment variable."
        )
    try:
        openai.api_key = key
        openai.Model.list()  # type: ignore Test the API key
    except AuthenticationError as e:
        raise UserError(f"OpenAI gave an Authentication Error:\n{e}")


def is_test_environment():
    """Returns True if in pytest and not benchmarks"""
    benchmarks_running = os.getenv("MENTAT_BENCHMARKS_RUNNING")
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        and "--benchmark" not in sys.argv
        and (not bool(benchmarks_running) or benchmarks_running == "false")
    )


async def _add_newline(response: AsyncGenerator[Any, None]):
    """
    The model normally ends it's response without a newline,
    but since our parsing relies on newlines to determine if a line is
    conversation or part of our format, adding a newline to the end
    makes everything much easier.
    """
    async for chunk in response:
        yield chunk
    yield {"choices": [{"delta": {"content": "\n"}}]}


def raise_if_in_test_environment():
    if is_test_environment():
        logging.critical("OpenAI call attempted in non benchmark test environment!")
        raise MentatError("OpenAI call attempted in non benchmark test environment!")


def warn_user(message: str, max_tries: int, details: Details):
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    warning = f"{message}: Retry number {details['tries']}/{max_tries - 1}..."
    stream.send(warning, color="light_yellow")


@backoff.on_exception(
    wait_gen=backoff.expo,
    exception=Timeout,
    max_tries=5,
    base=2,
    factor=2,
    jitter=None,
    logger="",
    giveup_log_level=logging.INFO,
    on_backoff=partial(warn_user, "Error reaching OpenAI's servers", 5),
)
@backoff.on_exception(
    wait_gen=backoff.expo,
    exception=RateLimitError,
    max_tries=3,
    base=2,
    factor=10,
    jitter=None,
    logger="",
    giveup_log_level=logging.INFO,
    on_backoff=partial(warn_user, "Rate limit recieved from OpenAI's servers", 3),
)
async def call_llm_api(
    messages: list[dict[str, str]], model: str
) -> AsyncGenerator[Any, None]:
    raise_if_in_test_environment()
    session_context = SESSION_CONTEXT.get()
    config = session_context.config

    response: AsyncGenerator[Any, None] = cast(
        AsyncGenerator[Any, None],
        await openai.ChatCompletion.acreate(  # type: ignore
            model=model,
            messages=messages,
            temperature=config.temperature,
            stream=True,
        ),
    )

    return _add_newline(response)


async def call_llm_api_sync(model: str, messages: list[dict[str, str]]) -> str:
    raise_if_in_test_environment()

    session_context = SESSION_CONTEXT.get()
    config = session_context.config

    response = await openai.ChatCompletion.acreate(  # type: ignore
        model=model,
        messages=messages,
        temperature=config.temperature,
    )

    # Create output features from the response
    return cast(str, response["choices"][0]["message"]["content"])  # type: ignore


async def call_embedding_api(
    input: list[str], model: str = "text-embedding-ada-002"
) -> list[list[float]]:
    raise_if_in_test_environment()

    response = await openai.Embedding.acreate(input=input, model=model)  # type: ignore
    return [i["embedding"] for i in response["data"]]  # type: ignore


# Ensures that each chunk will have at most one newline character
def chunk_to_lines(chunk: Any) -> list[str]:
    return chunk["choices"][0]["delta"].get("content", "").splitlines(keepends=True)


# NOTE: We may be calculating the length of Conversation messages incorrectly,
# but the difference should be negligible (<5 tokens per message):
# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def count_tokens(message: str, model: str) -> int:
    try:
        return len(
            tiktoken.encoding_for_model(model).encode(message, disallowed_special=())
        )
    except KeyError:
        return len(
            tiktoken.encoding_for_model("gpt-4").encode(message, disallowed_special=())
        )


def is_model_available(model: str) -> bool:
    available_models: list[str] = cast(
        list[str], [x["id"] for x in openai.Model.list()["data"]]  # type: ignore
    )

    return model in available_models


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


def get_prompt_token_count(messages: list[dict[str, str]], model: str) -> int:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    prompt_token_count = 0
    for message in messages:
        prompt_token_count += count_tokens(message["content"], model)
    stream.send(f"Total token count: {prompt_token_count}", color="cyan")

    token_buffer = 500
    context_size = model_context_size(model)
    if context_size:
        if prompt_token_count > context_size - token_buffer:
            stream.send(
                f"Warning: {model} has a maximum context length of {context_size}"
                " tokens. Attempting to run anyway:",
                color="yellow",
            )
    return prompt_token_count


@dataclass
class CostTracker:
    total_tokens: int = 0
    total_cost: float = 0

    def display_api_call_stats(
        self,
        num_prompt_tokens: int,
        num_sampled_tokens: int,
        model: str,
        call_time: float,
        decimal_places: int = 2,
    ) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        speed_and_cost_string = ""
        self.total_tokens += num_prompt_tokens + num_sampled_tokens
        if num_sampled_tokens > 0:
            tokens_per_second = num_sampled_tokens / call_time
            speed_and_cost_string += (
                f"Speed: {tokens_per_second:.{decimal_places}f} tkns/s"
            )
        cost = model_price_per_1000_tokens(model)
        if cost:
            prompt_cost = (num_prompt_tokens / 1000) * cost[0]
            sampled_cost = (num_sampled_tokens / 1000) * cost[1]
            call_cost = prompt_cost + sampled_cost
            self.total_cost += call_cost
            if speed_and_cost_string:
                speed_and_cost_string += " | "
            speed_and_cost_string += f"Cost: ${call_cost:.{decimal_places}f}"
        stream.send(speed_and_cost_string, color="cyan")

        costs_logger = logging.getLogger("costs")
        costs_logger.info(speed_and_cost_string)

    def display_total_cost(self) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        stream.send(f"Total session cost: ${self.total_cost:.2f}", color="light_blue")
