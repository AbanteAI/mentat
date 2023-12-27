import asyncio
from collections import deque
from rich import print
import re

from mentat.utils import dd, dump


class StreamingPrinter:
    def __init__(self):
        self.strings_to_print = deque[str]([])
        self.words_remaining = 0
        self.finishing = False
        self.shutdown = False

    def add_string(self, string: str, end: str = "\n", color: str | None = None):
        if self.finishing:
            return

        words = string.split(" ")

        for word in words:
            if word:
                if color is not None:
                    colored_word = f"[{color}]{word}[/{color}]"
                else:
                    colored_word = word
                self.strings_to_print.append(colored_word)
                self.words_remaining += 1

            self.strings_to_print.append(end)
            self.words_remaining += 1

    def sleep_time(self) -> float:
        max_finish_time = 1.0
        required_sleep_time = max_finish_time / (self.words_remaining + 1)
        max_sleep = 0.002 if self.finishing else 0.006
        min_sleep = 0.002
        return max(min(max_sleep, required_sleep_time), min_sleep)

    async def print_lines(self):
        while not self.shutdown:
            if self.strings_to_print:
                next_word = self.strings_to_print.popleft()
                print(next_word, end=" ", flush=True)
                self.words_remaining -= 1
            elif self.finishing:
                break
            await asyncio.sleep(self.sleep_time())

    def wrap_it_up(self):
        self.finishing = True

    def shutdown_printer(self):
        self.shutdown = True
