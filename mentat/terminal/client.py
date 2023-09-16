import argparse
import asyncio
import traceback
from typing import Iterable

from ipdb import set_trace
from prompt_toolkit import HTML, print_formatted_text
from termcolor import colored, cprint

from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_conversation import SessionConversation
from mentat.terminal.prompt_session import MentatPromptSession

setup_logging()


# TODO: handle exceptions
async def cprint_stream(conversation: SessionConversation):
    async for event in conversation.listen():
        message = event.message
        if "color" in message.extra:
            message_color = message.extra["color"]
            message_content = HTML(
                f"<{message_color}>{message.content}</{message_color}>"
            )
        else:
            message_content = message.content
        print_formatted_text(message_content)


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
