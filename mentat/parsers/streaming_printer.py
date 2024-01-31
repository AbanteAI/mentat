import asyncio
from collections import deque
from typing import Any, Dict, Tuple

from mentat.session_context import SESSION_CONTEXT

FormattedString = str | Tuple[str, Dict[str, Any]]


class StreamingPrinter:
    def __init__(self):
        self.strings_to_print: deque[Tuple[str, Dict[str, Any]]] = deque()
        self.chars_remaining = 0
        self.finishing = False
        self.shutdown = False

    def add_string(
        self,
        formatted_string: FormattedString,
        end: str = "\n",
    ):
        if self.finishing:
            return

        if isinstance(formatted_string, str):
            string = formatted_string
            styles = {}
        else:
            string = formatted_string[0]
            styles = formatted_string[1]
        if len(string) == 0:
            return
        string += end

        self.strings_to_print.extend((char, styles) for char in string)
        self.chars_remaining += len(string)

    def sleep_time(self) -> float:
        max_finish_time = 1.0
        required_sleep_time = max_finish_time / (self.chars_remaining + 1)
        max_sleep = 0.002 if self.finishing else 0.006
        min_sleep = 0.001
        return max(min(max_sleep, required_sleep_time), min_sleep)

    async def print_lines(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        while not self.shutdown:
            if self.strings_to_print:
                next_string = self.strings_to_print.popleft()
                stream.send(next_string[0], end="", flush=True, **next_string[1])
                self.chars_remaining -= 1
            elif self.finishing:
                break
            await asyncio.sleep(self.sleep_time())

    def wrap_it_up(self):
        self.finishing = True

    def shutdown_printer(self):
        self.shutdown = True
