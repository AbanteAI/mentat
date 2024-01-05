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
    """
    Do NOT mix termcolor colored with prompt_toolkit FormattedText! If colored text gets sent here and
    color is not None, the FormattedText will undo the colored text and display all of the ANSI codes.
    """
    if color is not None:
        f_color = color.replace("_", "").replace("light", "bright")
        if f_color != "" and not f_color.startswith("ansi"):
            f_color = "ansi" + f_color
        print_formatted_text(FormattedText([(f_color, content)]), end=end, flush=flush)
    else:
        print(content, end=end, flush=True)


def print_stream_message(message: StreamMessage, theme: dict[str, str] | None):
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
        if isinstance(message.extra.get("style"), str):
            style = message.extra["style"]
            if theme is not None:
                color = theme[style]

    _print_stream_message_string(
        content=message.data,
        end=end,
        color=color,
        flush=flush,
    )
