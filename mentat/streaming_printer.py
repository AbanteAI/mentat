import asyncio
from collections import deque

from termcolor import colored

from mentat.session_context import SESSION_CONTEXT
from mentat.terminal.themes import themes


class StreamingPrinter:
    def __init__(self):
        self.strings_to_print = deque[str]([])
        self.chars_remaining = 0
        self.finishing = False
        self.shutdown = False

    def add_string(
        self,
        string: str,
        end: str = "\n",
        color: str | None = None,
        style: str | None = None,
    ):
        if style is not None:
            session_context = SESSION_CONTEXT.get()
            if session_context.config.theme is not None:
                theme = themes.get(session_context.config.theme)
            else:
                theme = None
            if theme is not None:
                color = theme[style]

        if self.finishing:
            return

        if len(string) == 0:
            return
        string += end

        colored_string = colored(string, color) if color is not None else string

        index = colored_string.index(string)
        characters = list(string)
        characters[0] = colored_string[:index] + characters[0]
        characters[-1] = characters[-1] + colored_string[index + len(string) :]

        self.strings_to_print.extend(characters)
        self.chars_remaining += len(characters)

    def sleep_time(self) -> float:
        max_finish_time = 1.0
        required_sleep_time = max_finish_time / (self.chars_remaining + 1)
        max_sleep = 0.002 if self.finishing else 0.006
        min_sleep = 0.002
        return max(min(max_sleep, required_sleep_time), min_sleep)

    async def print_lines(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        while not self.shutdown:
            if self.strings_to_print:
                if len(self.strings_to_print) > 500:
                    next_string = "".join(self.strings_to_print)
                    self.strings_to_print = deque[str]([])
                else:
                    next_string = self.strings_to_print.popleft()
                stream.send(next_string, end="", flush=True)
                self.chars_remaining -= 1
            elif self.finishing:
                break
            await asyncio.sleep(self.sleep_time())

    def wrap_it_up(self):
        self.finishing = True

    def shutdown_printer(self):
        self.shutdown = True
