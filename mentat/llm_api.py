import logging
import os
import sys
from dataclasses import dataclass
from typing import Generator

import openai
import openai.error
import tiktoken
from dotenv import load_dotenv

from mentat.session_conversation import SessionConversation

from .config_manager import mentat_dir_path, user_config_path
from .errors import MentatError, UserError

package_name = __name__.split(".")[0]


# Check for .env file or already exported API key
# If no api key found, raise an error
def setup_api_key():
    mentat_dir_path / ".env"
    if not load_dotenv(mentat_dir_path / ".env"):
        load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise UserError(
            "No OpenAI api key detected.\nEither place your key into a .env"
            " file or export it as an environment variable."
        )
    try:
        openai.api_key = key
        openai.Model.list()  # Test the API key
    except openai.error.AuthenticationError as e:
        raise UserError(f"OpenAI gave an Authentication Error:\n{e}")


async def call_llm_api(messages: list[dict[str, str]], model) -> Generator:
    if (
        "PYTEST_CURRENT_TEST" in os.environ
        and "--benchmark" not in sys.argv
        and os.getenv("MENTAT_BENCHMARKS_RUNNING") == "false"
    ):
        logging.critical("OpenAI call attempted in non benchmark test environment!")
        raise MentatError("OpenAI call attempted in non benchmark test environment!")

    response = await openai.ChatCompletion.acreate(
        model=model,
        messages=messages,
        temperature=0.5,
        stream=True,
    )

    return response


def count_tokens(message: str) -> int:
    return len(
        tiktoken.encoding_for_model("gpt-4").encode(message, disallowed_special=())
    )


async def check_model_availability(
    allow_32k: bool, session_conversation: SessionConversation
) -> bool:
    available_models = [x["id"] for x in openai.Model.list()["data"]]
    if allow_32k:
        # check if user has access to gpt-4-32k
        if "gpt-4-32k-0314" not in available_models:
            await session_conversation.send_message(
                source="server",
                data=dict(
                    content="You set ALLOW_32K to true, but your OpenAI API key doesn't"
                    " have access to gpt-4-32k-0314. To remove this warning, set"
                    " ALLOW_32K to false until you have access.",
                    color="yellow",
                ),
            )
            allow_32k = False

    if not allow_32k:
        # check if user has access to gpt-4
        if "gpt-4-0314" not in available_models:
            raise UserError(
                "Sorry, but your OpenAI API key doesn't have access to gpt-4-0314,"
                " which is currently required to run Mentat."
            )

    return allow_32k


async def choose_model(
    messages: list[dict[str, str]],
    allow_32k: bool,
    session_conversation: SessionConversation,
) -> str:
    prompt_token_count = 0
    for message in messages:
        prompt_token_count += count_tokens(message["content"])
    await session_conversation.send_message(
        source="server",
        data=dict(content=f"Total token count: {prompt_token_count}", color="cyan"),
    )

    model = "gpt-4-0314"
    token_buffer = 500
    if prompt_token_count > 8192 - token_buffer:
        if allow_32k:
            model = "gpt-4-32k-0314"
            if prompt_token_count > 32768 - token_buffer:
                await session_conversation.send_message(
                    source="server",
                    data=dict(
                        content="Warning: gpt-4-32k-0314 has a token limit of 32768. Attempting"
                        " to run anyway:"
                    ),
                )
        else:
            await session_conversation.send_message(
                source="server",
                data=dict(
                    content="Warning: gpt-4-0314 has a maximum context length of 8192 tokens."
                    " If you have access to gpt-4-32k-0314, set allow-32k to `true` in"
                    f" `{user_config_path}` to use"
                    " it. Attempting to run with gpt-4-0314:",
                    color="yellow",
                ),
            )
    return model, prompt_token_count


@dataclass
class CostTracker:
    def __init__(self, session_conversation: SessionConversation):
        self.session_conversation = session_conversation
        self.total_cost = 0

    async def display_api_call_stats(
        self,
        num_prompt_tokens: int,
        num_sampled_tokens: int,
        model: str,
        call_time: float,
    ) -> None:
        cost_per_1000_tokens = {
            "gpt-4-0314": (0.03, 0.06),
            "gpt-4-32k-0314": (0.06, 0.12),
        }
        prompt_cost = (num_prompt_tokens / 1000) * cost_per_1000_tokens[model][0]
        sampled_cost = (num_sampled_tokens / 1000) * cost_per_1000_tokens[model][1]

        tokens_per_second = num_sampled_tokens / call_time
        call_cost = prompt_cost + sampled_cost

        speed_and_cost_string = (
            f"Speed: {tokens_per_second:.2f} tkns/s | Cost: ${call_cost:.2f}"
        )
        await self.session_conversation.send_message(
            source="server", data=dict(content=speed_and_cost_string, color="cyan")
        )

        costs_logger = logging.getLogger("costs")
        costs_logger.info(speed_and_cost_string)

        self.total_cost += call_cost

    async def display_total_cost(self) -> None:
        await self.session_conversation.send_message(
            source="server",
            data=dict(
                content=f"Total session cost: ${self.total_cost:.2f}",
                color="light_blue",
            ),
        )
