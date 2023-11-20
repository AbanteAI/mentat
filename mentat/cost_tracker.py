import logging
from dataclasses import dataclass

from mentat.llm_api_handler import model_price_per_1000_tokens
from mentat.session_context import SESSION_CONTEXT


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
