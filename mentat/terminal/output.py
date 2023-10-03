from typing import Any

from termcolor import cprint

from mentat.session_stream import StreamMessage


def _print_stream_message_string(
    content: Any,
    end: str = "\n",
    color: str | None = None,
    flush: bool = False,
):
    if color is not None:
        cprint(content, end=end, color=color, flush=flush)
    else:
        print(content, end=end, flush=flush)


def print_stream_message(message: StreamMessage):
    end = "\n"
    color = None
    flush = False
    if message.extra:
        if isinstance(message.extra.get("end"), str):
            end = message.extra["end"]
        if isinstance(message.extra.get("color"), str):
            color = message.extra["color"]
        if isinstance(message.extra.get("flush"), bool):
            flush = message.extra["flush"]

    _print_stream_message_string(
        content=message.data,
        end=end,
        color=color,
        flush=flush,
    )
