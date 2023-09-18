import argparse
import asyncio
import traceback
from typing import Dict, Iterable, List

from ipdb import set_trace
from prompt_toolkit import HTML, print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from termcolor import colored, cprint

from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_conversation import Message, SessionConversation
from mentat.terminal.prompt_session import MentatPromptSession

setup_logging()


def format_message_content(
    content: str,
    color: str | None = None,
    end: str | None = None,
    use_ansi_colors: bool = True,
):
    formatted_content = content + (end if end is not None else "\n")
    formatted_color = color if color is not None else ""
    if (
        formatted_color != ""
        and use_ansi_colors
        and not formatted_color.startswith("ansi")
    ):
        formatted_color = "ansi" + formatted_color

    return (formatted_color, formatted_content)


def format_and_print_text(message: Message, use_ansi_colors: bool = True):
    formatted_text = []
    if isinstance(message.data, list):
        for data in message.data:
            _formatted_text = format_message_content(
                content=data["content"],
                color=data.get("color"),
                end=data.get("end"),
            )
            formatted_text.append(_formatted_text)
    else:
        _formatted_text = format_message_content(
            content=message.data.content,
            color=message.data.get("color"),
            end=message.data.get("end"),
        )

    print_formatted_text(FormattedText(formatted_text))


# TODO: handle exceptions
async def cprint_stream(conversation: SessionConversation):
    async for event in conversation.listen():
        message = event.message
        format_and_print_text(message)


class TerminalClient:
    def __init__(self):
        self.engine = Engine()
        self.engine_task: asyncio.Task | None = None

        self._prompt_session = MentatPromptSession(self.engine)

    async def get_user_input(self) -> str:
        cprint("waiting for user input:")
        user_input = await self._prompt_session.prompt_async()
        cprint(f"got user input: {user_input}")
        if user_input == "q":
            raise KeyboardInterrupt
        return user_input

    async def _run(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
    ):
        self.engine_task = asyncio.create_task(self.engine._run())
        try:
            self.session = await self.engine.create_session(
                paths, exclude_paths, no_code_map
            )
            listen_to_conv = asyncio.create_task(
                cprint_stream(self.session.session_conversation)
            )
            while True:
                user_input = await self.get_user_input()
                await self.session.session_conversation.add_message(user_input)
        except KeyboardInterrupt:
            cprint("KeyboardInterrupt", color="yellow")
        except Exception as e:
            cprint(f"Exception: {e}", color="red")
        finally:
            self.engine._should_exit = True
            assert self.engine_task
            await self.engine_task
            self.engine_task = None

    def run(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
    ):
        asyncio.run(self._run(paths, exclude_paths, no_code_map))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run conversation with command line args"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="List of file paths, directory paths, or glob patterns",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        nargs="*",
        default=[],
        help="List of file paths, directory paths, or glob patterns to exclude",
    )
    parser.add_argument(
        "--no-code-map",
        action="store_true",
        help="Exclude the file structure/syntax map from the system prompt",
    )
    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    no_code_map = args.no_code_map

    terminal_client = TerminalClient()
    terminal_client.run(paths, exclude_paths, no_code_map)
