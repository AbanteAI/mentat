import argparse
import asyncio
import logging
import signal
import traceback
from typing import Coroutine, List, Set
from uuid import UUID

from ipdb import set_trace
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer

from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_stream import StreamMessageSource
from mentat.terminal.output import cprint, cprint_stream_message
from mentat.terminal.prompt_completer import MentatCompleter
from mentat.terminal.prompt_session import MentatPromptSession

# Move this to the cli file?
setup_logging()

logger = logging.getLogger("mentat.terminal")
logger.setLevel(logging.DEBUG)


class TerminalClient:
    def __init__(self):
        self.session = Session()

        self._tasks: Set[asyncio.Task] = set()
        self._prompt_session = MentatPromptSession(message=[("class:prompt", ">>> ")])
        self._should_exit = False
        self._force_exit = False

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

    async def _handle_input_requests(self, prompt_completer: Completer | None = None):
        # async for message in self.session.stream.listen("input_request"):
        #     await self._input_queue.put(message)

        # input_request_message = await self._input_queue.get()

        while True:
            input_request_message = await self.session.stream.recv("input_request")

            user_input = await self._prompt_session.prompt_async(
                handle_sigint=False, completer=prompt_completer
            )
            if user_input == "q":
                self._should_exit = True
                return

            await self.session.stream.send(
                user_input,
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )

    async def _send_session_stream_interrupt(self):
        await self.session.stream.send(
            "", source=StreamMessageSource.CLIENT, channel="interrupt"
        )

    def _handle_exit(self):
        if (
            self.session.is_stopped
            or self.session.stream.interrupt_lock.locked() is False
        ):
            if self._should_exit:
                logger.debug("Force exiting client...")
                self._force_exit = True
            else:
                logger.debug("Should exit client...")
                self._should_exit = True

        else:
            logger.debug("Sending interrupt to session stream")
            self._create_task(self._send_session_stream_interrupt())

    def _init_signal_handlers(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._handle_exit)
        loop.add_signal_handler(signal.SIGTERM, self._handle_exit)

    async def _startup(self):
        logger.debug("Running startup")
        self.session.start()

        # mentat_completer = MentatCompleter(self.session)
        # self._create_task(mentat_completer.refresh_completions())
        mentat_completer = None

        self._create_task(self._cprint_session_stream())
        self._create_task(self._handle_input_requests())

        logger.debug("Completed startup")

    async def _shutdown(self):
        logger.debug("Running shutdown")

        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        logger.debug("Waiting for background tasks to finish. (CTRL+C to force quit)")
        while not self._force_exit:
            if all([task.cancelled() for task in self._tasks]):
                break
            await asyncio.sleep(0.1)

        # Stop session
        self.session.stop()
        while not self._force_exit and not self.session.is_stopped:
            await asyncio.sleep(0.1)

        logger.debug("Completed shutdown")

    async def _main(self):
        logger.debug("Running main loop")

        counter = 0
        while not self._should_exit and not self.session.is_stopped:
            counter += 1
            counter = counter % 86400
            await asyncio.sleep(0.1)

    async def _run(
        self,
        paths: List[str] | None = [],
        exclude_paths: List[str] | None = [],
        no_code_map: bool = False,
    ):
        try:
            self._init_signal_handlers()
            await self._startup()
            await self._main()
            await self._shutdown()
        # NOTE: if an exception is caught here, the main process will likely still run
        # due to background ascynio Tasks that are still running
        except Exception as e:
            logger.error(f"Unexpected Exception {e}")
            logger.error(traceback.format_exc())

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
