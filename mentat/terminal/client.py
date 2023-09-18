import argparse
import asyncio
import traceback
from typing import Dict, Iterable, List

from ipdb import set_trace
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText

from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_conversation import Message, SessionConversation
from mentat.terminal.prompt_session import MentatPromptSession

setup_logging()

# TODO:
# - validate ansi colors (add typing for color literals?)


def cprint(text: str, color: str | None = None, use_ansi_colors: bool = True):
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


def format_message_content(
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


def format_and_print_message(message: Message, use_ansi_colors: bool = True):
    formatted_text = []
    if isinstance(message.data, list):
        for data in message.data:
            _formatted_text = format_message_content(
                content=data["content"],
                color=data.get("color"),
                end=data.get("end"),
                use_ansi_colors=use_ansi_colors,
            )
            formatted_text.append(_formatted_text)
    elif "content" in message.data:
        _formatted_text = format_message_content(
            content=message.data["content"],
            color=message.data.get("color"),
            end=message.data.get("end"),
            use_ansi_colors=use_ansi_colors,
        )
        formatted_text.append(_formatted_text)
    else:
        return
    print_formatted_text(FormattedText(formatted_text))


class TerminalClient:
    def __init__(self):
        self.engine = Engine()
        self.engine_task: asyncio.Task | None = None

        self._prompt_session = MentatPromptSession(self.engine)
        self._input_queue = asyncio.Queue()

    async def stream_conversation(self, conversation: SessionConversation):
        try:
            async for message in conversation.listen():
                format_and_print_message(message)

                if "type" in message.data:
                    if message.data["type"] == "collect_user_input":
                        self._input_queue.put_nowait(message)
        except Exception as e:
            set_trace()
            cprint(f"There was an exception: {e}")
            traceback.print_exc()

    async def handle_user_input(self, conversation: SessionConversation) -> str:
        while True:
            input_request_message = await self._input_queue.get()
            cprint("waiting for user input:")
            user_input = await self._prompt_session.prompt_async()
            cprint(f"got user input: {user_input}")
            if user_input == "q":
                raise KeyboardInterrupt

            await conversation.send_message(
                source="client",
                data={"content": user_input},
                channel=f"default:{input_request_message.id}",
            )

    async def _run(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
    ):
        self.engine_task = asyncio.create_task(self.engine._run())
        try:
            session = await self.engine.create_session(
                paths, exclude_paths, no_code_map
            )
            stream_conversation_task = asyncio.create_task(
                self.stream_conversation(session.session_conversation)
            )
            await self.handle_user_input(session.session_conversation)
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
