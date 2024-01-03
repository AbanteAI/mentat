import logging
from dataclasses import dataclass
from timeit import default_timer
from typing import AsyncIterator, Optional

from openai.types.chat import ChatCompletionChunk

from mentat.llm_api_handler import count_tokens, model_price_per_1000_tokens
from mentat.session_context import SESSION_CONTEXT


@dataclass
class CostTracker:
    total_tokens: int = 0
    total_cost: float = 0

    last_api_call: str = ""

    def log_api_call_stats(
        self,
        num_prompt_tokens: int,
        num_sampled_tokens: int,
        model: str,
        call_time: Optional[float] = None,
        decimal_places: int = 2,
        display: bool = False,
    ) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        speed_and_cost_string = ""
        self.total_tokens += num_prompt_tokens + num_sampled_tokens
        if num_sampled_tokens > 0 and call_time is not None:
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
        if display:
            stream.send(speed_and_cost_string, style="info")

        costs_logger = logging.getLogger("costs")
        costs_logger.info(speed_and_cost_string)
        self.last_api_call = speed_and_cost_string

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

    def display_total_cost(self) -> None:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        stream.send(f"Total session cost: ${self.total_cost:.2f}", style="info")

    async def response_logger_wrapper(
        self,
        prompt_tokens: int,
        response: AsyncIterator[ChatCompletionChunk],
        model: str,
    ) -> AsyncIterator[ChatCompletionChunk]:
        full_response = ""
        start_time = default_timer()
        async for chunk in response:
            # On Azure OpenAI, the first chunk streamed may contain only metadata relating to content filtering.
            if len(chunk.choices) == 0:
                continue
            full_response += chunk.choices[0].delta.content or ""
            yield chunk
        time_elapsed = default_timer() - start_time
        self.log_api_call_stats(
            prompt_tokens,
            count_tokens(full_response, model, full_message=False),
            model,
            time_elapsed,
        )
