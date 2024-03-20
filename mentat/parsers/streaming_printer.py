import asyncio
from collections import deque
from typing import Any, Dict, List, Literal, Tuple

from mentat.session_context import SESSION_CONTEXT

# TODO: Make this a class
FormattedString = str | Tuple[str, Dict[str, Any]] | List[Tuple[str, Dict[str, Any]]]


def send_formatted_string(string: FormattedString):
    ctx = SESSION_CONTEXT.get()

    if isinstance(string, List):
        for line in string:
            ctx.stream.send(line[0], **line[1], end="")
        ctx.stream.send("")
    elif isinstance(string, str):
        ctx.stream.send(string)
    else:
        ctx.stream.send(string[0], **string[1])


class StreamingPrinter:
    def __init__(self):
        self.strings_to_print: deque[Tuple[str, Dict[str, Any]]] = deque()
        self.finishing = False
        self.shutdown = False
        self.cur_file: str | None = None
        self.cur_file_display: Tuple[str, Literal["edit", "creation", "deletion", "rename"]] | None = None

    def add_string(
        self,
        formatted_string: FormattedString,
        end: str = "\n",
        allow_empty: bool = False,
    ):
        if self.finishing:
            return

        if isinstance(formatted_string, List):
            for string in formatted_string:
                self.add_string(string, end="")
            if end and (allow_empty or any(string[0] for string in formatted_string)):
                self.add_string(end, end="")
            return
        if isinstance(formatted_string, str):
            string = formatted_string
            styles = {}
        else:
            string = formatted_string[0]
            styles = formatted_string[1]

        styles["filepath"] = self.cur_file
        styles["filepath_display"] = list(self.cur_file_display) if self.cur_file_display else None
        if not string:
            if allow_empty:
                self.strings_to_print.append(("", styles))
            return

        self.strings_to_print.extend((char, styles) for char in string)
        if end:
            self.add_string(end, end="")

    def add_delimiter(self):
        self.add_string(("", {"delimiter": True}), end="", allow_empty=True)

    def sleep_time(self) -> float:
        max_finish_time = 1.0
        required_sleep_time = max_finish_time / (len(self.strings_to_print) + 1)
        max_sleep = 0.002 if self.finishing else 0.006
        min_sleep = 0.001
        return max(min(max_sleep, required_sleep_time), min_sleep)

    async def print_lines(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        while not self.shutdown:
            if self.strings_to_print:
                next_string = self.strings_to_print.popleft()
                stream.send(next_string[0], end="", **next_string[1])
            elif self.finishing:
                break
            await asyncio.sleep(self.sleep_time())

    def wrap_it_up(self):
        self.finishing = True

    def shutdown_printer(self):
        self.shutdown = True
