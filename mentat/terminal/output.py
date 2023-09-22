from ipdb import set_trace
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

from mentat.session_stream import StreamMessage


def cprint(text: str, color: str | None = None, use_ansi_colors: bool = True):
    """Custom cprint to work with asyncio and prompt toolkit

    TODO:
        - validate ansi colors (add typing for color literals?)
    """
    formatted_color = color if color is not None else ""
    formatted_color = formatted_color.replace("_", "").replace("light", "bright")
    if (
        formatted_color != ""
        and use_ansi_colors
        and not formatted_color.startswith("ansi")
    ):
        formatted_color = "ansi" + formatted_color
    formatted_text = FormattedText([(formatted_color, text)])
    print_formatted_text(formatted_text)


def _cprint_stream_message_string(
    content: str,
    end: str = "\n",
    color: str | None = None,
    use_ansi_colors: bool = True,
):
    formatted_color = color if color is not None else ""
    formatted_color = formatted_color.replace("_", "").replace("light", "bright")
    if (
        formatted_color != ""
        and use_ansi_colors
        and not formatted_color.startswith("ansi")
    ):
        formatted_color = "ansi" + formatted_color

    print_formatted_text(FormattedText([(formatted_color, content)]), end=end)


def cprint_stream_message(message: StreamMessage, use_ansi_colors: bool = True):
    end = "\n"
    color = None
    if message.extra:
        if isinstance(message.extra.get("end"), str):
            end = message.extra["end"]
        if isinstance(message.extra.get("color"), str):
            color = message.extra["color"]

    if isinstance(message.data, str):
        _cprint_stream_message_string(
            content=message.data, end=end, color=color, use_ansi_colors=use_ansi_colors
        )
    else:
        set_trace()
        print_formatted_text(message.data, end=end)
