from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

from mentat.session_conversation import Message


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


def _format_message_content(
    content: str,
    color: str | None = None,
    end: str | None = None,
    use_ansi_colors: bool = True,
):
    formatted_content = content + (end if end is not None else "\n")
    formatted_color = color if color is not None else ""
    formatted_color = formatted_color.replace("_", "").replace("light", "bright")
    if (
        formatted_color != ""
        and use_ansi_colors
        and not formatted_color.startswith("ansi")
    ):
        formatted_color = "ansi" + formatted_color

    return (formatted_color, formatted_content)


def _cprint_message(message: Message, use_ansi_colors: bool = True):
    message_content = _format_message_content(
        content=message.data["content"],
        color=message.data.get("color"),
        end=message.data.get("end"),
        use_ansi_colors=use_ansi_colors,
    )
    print_formatted_text(
        FormattedText([message_content]), end=message.data.get("end"), flush=True
    )


def cprint_message(message: Message, use_ansi_colors: bool = True):
    formatted_text = []
    if isinstance(message.data, list):
        for data in message.data:
            _formatted_text = _format_message_content(
                content=data["content"],
                color=data.get("color"),
                end=data.get("end"),
                use_ansi_colors=use_ansi_colors,
            )
            formatted_text.append(_formatted_text)
    elif "content" in message.data:
        _cprint_message(message)
        return
    else:
        return
    print_formatted_text(FormattedText(formatted_text))
