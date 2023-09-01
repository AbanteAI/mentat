import asyncio
from collections import deque


class StreamingPrinter:
    def __init__(self, interface):
        self.interface = interface
        self.strings_to_print = deque([])
        self.chars_remaining = 0
        self.shutdown = False

    def add_string(self, string, end="\n", color=None):
        if len(string) == 0:
            return
        string += end
        characters = list(string)
        self.strings_to_print.extend(characters)
        self.chars_remaining += len(characters)

    def sleep_time(self):
        max_finish_time = 1.0
        required_sleep_time = max_finish_time / (self.chars_remaining + 1)
        max_sleep = 0.002 if self.shutdown else 0.006
        min_sleep = 0.002
        return max(min(max_sleep, required_sleep_time), min_sleep)

    async def print_lines(self):
        while True:
            if self.strings_to_print:
                next_string = self.strings_to_print.popleft()
                self.interface.display(next_string, end="")
                self.chars_remaining -= 1
            elif self.shutdown:
                break
            await asyncio.sleep(self.sleep_time())

    def wrap_it_up(self):
        self.shutdown = True
