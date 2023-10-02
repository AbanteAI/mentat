from typing import Any

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

from mentat.session_stream import StreamMessage


def _print_stream_message_string(
    content: Any,
    end: str = "\n",
    color: str | None = None,
    flush: bool = False,
):
    if color:
        f_color = color.replace("_", "").replace("light", "bright")
        if f_color != "" and not f_color.startswith("ansi"):
            f_color = "ansi" + f_color
        print_formatted_text(FormattedText([(f_color, content)]), end=end, flush=flush)
    else:
        print(content, end=end, flush=True)


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
