import argparse
import asyncio
import logging
import signal
import traceback
from typing import Coroutine, List, Set
from uuid import UUID

from ipdb import set_trace

from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_stream import StreamMessageSource
from mentat.terminal.output import cprint, cprint_stream_message
from mentat.terminal.prompt_completer import MentatCompleter
from mentat.terminal.prompt_session import MentatPromptSession

# Move this to the cli file?
setup_logging()

logger = logging.getLogger("mentat.terminal")


class TerminalClient:
    def __init__(self):
        self.session = Session()

        self._tasks: Set[asyncio.Task] = set()
        self._prompt_session = MentatPromptSession(message=[("class:prompt", ">>> ")])

        # NOTE: should input requests be 'stackable'? Should there only be 1 input request at a time?
        self._input_queue = asyncio.Queue()

    def _create_task(self, coro: Coroutine):
        """Utility method for running a Task in the background"""

        def task_cleanup(task: asyncio.Task):
            self._tasks.remove(task)

        task = asyncio.create_task(coro)
        task.add_done_callback(task_cleanup)
        self._tasks.add(task)

        return task

    async def _cprint_session_stream(self):
        async for message in self.session.stream.listen():
            cprint_stream_message(message)

    async def _handle_input_requests(self):
        async for message in self.session.stream.listen("input_request"):
            self._input_queue.put_nowait(message)

    async def _send_session_stream_interrupt(self):
        await self.session.stream.send(
            "", source=StreamMessageSource.CLIENT, channel="interrupt"
        )

    async def _handle_user_input(self) -> str:
        # mentat_completer = MentatCompleter(self.engine, self.session_id)
        # self._create_task(mentat_completer.refresh_completions())
        mentat_completer = None

        while True:
            input_request_message = await self._input_queue.get()

            user_input = await self._prompt_session.prompt_async(
                handle_sigint=False, completer=mentat_completer
            )
            if user_input == "q":
                raise KeyboardInterrupt

            await self.session.stream.send(
                user_input,
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )

    # FIXME
    def _handle_exit(self):
        print("Terminal client got a signal")
        self._create_task(self._send_session_stream_interrupt())
        # if self._should_exit:
        #     self._force_exit = True
        # else:
        #     self._should_exit = True

    def _init_signal_handlers(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._handle_exit)
        loop.add_signal_handler(signal.SIGTERM, self._handle_exit)

    async def _startup(self):
        logger.debug("Starting Sesson...")
        self.session.start()

    async def _shutdown(self):
        logger.debug("Stopping Sesson...")
        self.session.stop()

    async def _main(
        self,
        paths: List[str] | None = [],
        exclude_paths: List[str] | None = [],
        no_code_map: bool = False,
    ):
        # TODO: shutdown this task properly
        _session_listen_task = asyncio.create_task(self._cprint_session_stream())
        _session_input_handler_task = asyncio.create_task(self._handle_input_requests())

        try:
            await self._handle_user_input()
        except KeyboardInterrupt:
            cprint("KeyboardInterrupt", color="yellow")

    async def _run(
        self,
        paths: List[str] | None = [],
        exclude_paths: List[str] | None = [],
        no_code_map: bool = False,
    ):
        self._init_signal_handlers()
        await self._startup()
        await self._main(paths, exclude_paths, no_code_map)
        await self._shutdown()

    def run(
        self,
        paths: List[str] | None = [],
        exclude_paths: List[str] | None = [],
        no_code_map: bool = False,
    ):
        asyncio.run(self._run(paths, exclude_paths, no_code_map))


def run_cli():
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
