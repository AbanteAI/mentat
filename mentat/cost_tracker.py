import logging
from dataclasses import dataclass
from timeit import default_timer
from typing import AsyncIterator, Optional

from openai.types.chat import ChatCompletionChunk
from spice import SpiceResponse

from mentat.llm_api_handler import count_tokens, model_price_per_1000_tokens
from mentat.session_context import SESSION_CONTEXT


@dataclass
class CostTracker:
    total_tokens: int = 0
    total_cost: float = 0

    last_api_call: str = ""

    def log_api_call_stats(
        self,
        response: SpiceResponse,
    ) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        decimal_places = 2

        model = response.call_args.model
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        total_time = response.total_time

        speed_and_cost_string = ""
        self.total_tokens += input_tokens + output_tokens
        if output_tokens > 0 and total_time is not None:
            tokens_per_second = output_tokens / total_time
            speed_and_cost_string += f"Speed: {tokens_per_second:.{decimal_places}f} tkns/s"
        cost = model_price_per_1000_tokens(model)
        if cost:
            prompt_cost = (input_tokens / 1000) * cost[0]
            sampled_cost = (output_tokens / 1000) * cost[1]
            call_cost = prompt_cost + sampled_cost
            self.total_cost += call_cost
            if speed_and_cost_string:
                speed_and_cost_string += " | "
            speed_and_cost_string += f"Cost: ${call_cost:.{decimal_places}f}"

        costs_logger = logging.getLogger("costs")
        costs_logger.info(speed_and_cost_string)
        self.last_api_call = speed_and_cost_string

    def log_embedding_call_stats(self, tokens, model, total_time):
        cost = model_price_per_1000_tokens(model)[0]
        call_cost = (tokens / 1000) * cost
        self.total_cost += call_cost
        costs_logger = logging.getLogger("costs")
        costs_logger.info(f"Cost: ${call_cost:.2f}")
        self.last_api_call = f"Embedding call time and cost: {total_time:.2f}s, ${call_cost:.2f}"

    def display_last_api_call(self):
        """
        Used so that places that call the llm can print the api call stats after they finish printing everything else.
        The api call will not be logged if it gets interrupted!
        """
        ctx = SESSION_CONTEXT.get()
        if self.last_api_call:
            ctx.stream.send(self.last_api_call, style="info")

    def log_whisper_call_stats(self, seconds: float):
        self.total_cost += seconds * 0.0001
