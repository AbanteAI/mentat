import argparse
import asyncio
import signal
import traceback
from typing import Iterable

from ipdb import set_trace

from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.session_conversation import SessionConversation
from mentat.terminal.output import cprint, cprint_message
from mentat.terminal.prompt_session import MentatPromptSession

# Move this to the cli file?
setup_logging()


class TerminalClient:
    def __init__(self):
        self.engine = Engine()
        self.engine_task: asyncio.Task | None = None

        self._prompt_session = MentatPromptSession(
            self.engine,
            message=[("class:prompt", ">>> ")],
        )

        # NOTE: should input requests be 'stackable'? Should there only be 1 input request at a time?
        self._input_queue = asyncio.Queue()

    async def stream_conversation(self, conversation: SessionConversation):
        try:
            async for message in conversation.listen():
                cprint_message(message)

                if "type" in message.data:
                    if message.data["type"] == "collect_user_input":
                        self._input_queue.put_nowait(message)
        except Exception as e:
            set_trace()
            cprint(f"There was an exception: {e}")
            traceback.print_exc()

    async def handle_user_input(self, conversation: SessionConversation) -> str:
        while True:
            try:
                input_request_message = await self._input_queue.get()
            except Exception as e:
                set_trace()
                raise e

            # cprint("waiting for user input:")
            user_input = await self._prompt_session.prompt_async()
            cprint(f"got user input: {user_input}")

            if user_input == "q":
                raise KeyboardInterrupt

            await conversation.send_message(
                source="client",
                data={"content": user_input},
                channel=f"default:{input_request_message.id}",
            )

    def _handle_exit(self):
        set_trace()
        if self._should_exit:
            self._force_exit = True
        else:
            self._should_exit = True

    def _init_signal_handlers(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._handle_exit)
        loop.add_signal_handler(signal.SIGTERM, self._handle_exit)

    async def _run(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
    ):
        self._init_signal_handlers()
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
            # Send "interrupt" message to engine
            # Engine handles where/how to route the interrupt message
            set_trace()
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
