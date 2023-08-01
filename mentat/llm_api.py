import logging
import os
import sys
from dataclasses import dataclass
from typing import Generator

import openai
import tiktoken
from dotenv import load_dotenv
from termcolor import cprint

from .config_manager import mentat_dir_path, user_config_path

model_8k = "gpt-4-0314"
model_32k = "gpt-4-32k-0314"
tokens_8k = 8192
tokens_32k = 32768
token_buffer = 500

cost_per_1000_tokens = {
    model_8k: (0.03, 0.06),
    model_32k: (0.06, 0.12),
}


# Check for .env file or already exported API key
# If no api key found, exit and warn user
def setup_api_key():
    if not load_dotenv(os.path.join(mentat_dir_path, ".env")):
        load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    try:
        openai.api_key = key
        openai.Model.list()  # Test the API key
    except openai.error.AuthenticationError:
        cprint(
            "No valid OpenAI api key detected.\nEither place your key into a .env"
            " file or export it as an environment variable.",
            "red",
        )
        sys.exit(0)


async def call_llm_api(messages: list[dict[str, str]], model) -> Generator:
    if (
        "PYTEST_CURRENT_TEST" in os.environ
        and "--benchmark" not in sys.argv
        and os.getenv("MENTAT_BENCHMARKS_RUNNING") == "false"
    ):
        logging.critical("OpenAI call made in non benchmark test environment!")
        sys.exit(1)

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


def get_prompt_token_count(messages: list[str]) -> int:
    prompt_token_count = 0
    for message in messages:
        prompt_token_count += count_tokens(message["content"])
    return prompt_token_count


def check_model_availability(allow_32k: bool) -> bool:
    available_models = [x["id"] for x in openai.Model.list()["data"]]
    if allow_32k:
        # check if user has access to gpt-4-32k
        if model_32k not in available_models:
            cprint(
                "You set ALLOW_32K to true, but your OpenAI API key doesn't"
                f" have access to {model_32k}. To remove this warning, set"
                " ALLOW_32K to false until you have access.",
                "yellow",
            )
            allow_32k = False

    if not allow_32k:
        # check if user has access to gpt-4
        if model_8k not in available_models:
            cprint(
                f"Sorry, but your OpenAI API key doesn't have access to {model_8k},"
                " which is currently required to run Mentat.",
                "red",
            )
            raise KeyboardInterrupt

    return allow_32k


def choose_model(prompt_token_count: int, allow_32k: bool) -> str:
    if prompt_token_count > tokens_8k - token_buffer:
        if allow_32k:
            if prompt_token_count > tokens_32k - token_buffer:
                cprint(
                    "\nWarning: gpt-4-32k-0314 has a token limit of"
                    f" {tokens_32k} tokens. Your current context length is"
                    f" {prompt_token_count} tokens. Attempting to run anyway:",
                    "light_yellow",
                )
            return model_32k
        else:
            cprint(
                f"\nWarning: gpt-4-0314 has a token limit of {tokens_8k} tokens. Your"
                f" current context length is {prompt_token_count} tokens. If you have"
                f" access to {model_32k}, set allow-32k to `true` in"
                f" `{user_config_path}` to use it. Attempting to run with {model_8k}:",
                "light_yellow",
            )
            return model_8k
    else:
        return model_8k


@dataclass
class CostTracker:
    total_cost: int = 0

    def display_api_call_stats(
        self,
        num_prompt_tokens: int,
        num_sampled_tokens: int,
        model: str,
        call_time: float,
    ) -> None:
        prompt_cost = (num_prompt_tokens / 1000) * cost_per_1000_tokens[model][0]
        sampled_cost = (num_sampled_tokens / 1000) * cost_per_1000_tokens[model][1]

        tokens_per_second = num_sampled_tokens / call_time
        call_cost = prompt_cost + sampled_cost

        speed_and_cost_string = (
            f"Speed: {tokens_per_second:.2f} tkns/s | Cost: ${call_cost:.2f}"
        )
        cprint(speed_and_cost_string, "cyan")

        costs_logger = logging.getLogger("costs")
        costs_logger.info(speed_and_cost_string)

        self.total_cost += call_cost

    def display_total_cost(self) -> None:
        cprint(f"\nTotal session cost: ${self.total_cost:.2f}", color="light_blue")
