import argparse
import asyncio
import logging
import signal
import traceback
from pathlib import Path
from typing import Any, Coroutine, List, Set

from ipdb import set_trace
from prompt_toolkit.completion import Completer

from mentat.session import Session
from mentat.session_stream import StreamMessageSource
from mentat.terminal.output import cprint_stream_message
from mentat.terminal.prompt_completer import MentatCompleter
from mentat.terminal.prompt_session import MentatPromptSession

logger = logging.getLogger("mentat.terminal")
logger.setLevel(logging.DEBUG)


class TerminalClient:
    def __init__(
        self,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        no_code_map: bool = False,
        diff: str | None = None,
        pr_diff: str | None = None,
    ):
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.no_code_map = no_code_map
        self.diff = diff
        self.pr_diff = pr_diff

        self.session: Session | None = None

        self._tasks: Set[asyncio.Task[None]] = set()
        self._prompt_session = MentatPromptSession(message=[("class:prompt", ">>> ")])
        self._should_exit = False
        self._force_exit = False

    def _create_task(self, coro: Coroutine[None, None, Any]):
        """Utility method for running a Task in the background"""

        def task_cleanup(task: asyncio.Task[None]):
            self._tasks.remove(task)

        task = asyncio.create_task(coro)
        task.add_done_callback(task_cleanup)
        self._tasks.add(task)

        return task

    async def _cprint_session_stream(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        async for message in self.session.stream.listen():
            if self._should_exit:
                return
            cprint_stream_message(message)

    async def _handle_input_requests(self, prompt_completer: Completer | None = None):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        while True:
            input_request_message = await self.session.stream.recv("input_request")

            # TODO: fix user_input typing
            user_input = await self._prompt_session.prompt_async(  # type: ignore
                completer=prompt_completer, handle_sigint=False
            )
            assert isinstance(user_input, str)
            if user_input == "q":
                self._should_exit = True
                return

            await self.session.stream.send(
                user_input,
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )

    async def _send_session_stream_interrupt(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        await self.session.stream.send(
            "", source=StreamMessageSource.CLIENT, channel="interrupt"
        )

    def _handle_exit(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"

        # set_trace()

        if (
            self.session.is_stopped
            or self.session.stream.interrupt_lock.locked() is False
        ):
            if self._should_exit:
                set_trace()
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
        assert self.session == None, "TerminalClient already running"

        logger.debug("Running startup")

        self.session = await Session.create(
            self.paths, self.exclude_paths, self.no_code_map, self.diff, self.pr_diff
        )
        self.session.start()

        mentat_completer = MentatCompleter(self.session)

        self._create_task(mentat_completer.refresh_completions())
        self._create_task(self._cprint_session_stream())
        self._create_task(self._handle_input_requests(mentat_completer))

        logger.debug("Completed startup")

    async def _shutdown(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"

        logger.debug("Running shutdown")

        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        logger.debug("Waiting for background tasks to finish. (CTRL+C to force quit)")
        while not self._force_exit:
            if all([task.cancelled() for task in self._tasks]):
                break
            await asyncio.sleep(0.01)

        # Stop session
        self.session.stop()
        while not self._force_exit and not self.session.is_stopped:
            await asyncio.sleep(0.01)
        self.session = None

        logger.debug("Completed shutdown")

    async def _main(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        logger.debug("Running main loop")

        while not self._should_exit and not self.session.is_stopped:
            await asyncio.sleep(0.01)

    async def _run(self):
        try:
            self._init_signal_handlers()
            await self._startup()
            await self._main()
            await self._shutdown()
        # NOTE: if an exception is caught here, the main process will likely still run
        # due to background ascynio Tasks that are still running
        # NOTE: we should remove this try/except. The code inside of `self._run` should
        # never throw an exception
        except Exception as e:
            set_trace()
            logger.error(f"Unexpected Exception {e}")
            logger.error(traceback.format_exc())

    def run(self):
        asyncio.run(self._run())


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
    parser.add_argument(
        "--diff",
        "-d",
        type=str,
        default=None,
        help="A git tree-ish (e.g. commit, branch, tag) to diff against",
    )
    parser.add_argument(
        "--pr-diff",
        "-p",
        type=str,
        default=None,
        help="A git tree-ish to diff against the latest common ancestor of",
    )
    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    no_code_map = args.no_code_map
    diff = args.diff
    pr_diff = args.pr_diff

    terminal_client = TerminalClient(paths, exclude_paths, no_code_map, diff, pr_diff)
    terminal_client.run()
