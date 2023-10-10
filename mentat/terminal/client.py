import argparse
import asyncio
import logging
import signal
from pathlib import Path
from types import FrameType
from typing import Any, Coroutine, List, Set

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.styles import Style

from mentat.config_manager import CONFIG_MANAGER
from mentat.include_files import expand_paths
from mentat.session import Session
from mentat.session_stream import StreamMessageSource
from mentat.terminal.output import print_stream_message
from mentat.terminal.prompt_completer import MentatCompleter
from mentat.terminal.prompt_session import MentatPromptSession


class TerminalClient:
    def __init__(
        self,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        no_code_map: bool = False,
        diff: str | None = None,
        pr_diff: str | None = None,
        auto_tokens: int | None = None,
    ):
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.no_code_map = no_code_map
        self.diff = diff
        self.pr_diff = pr_diff
        self.auto_tokens = auto_tokens

        self.session: Session | None = None

        self._tasks: Set[asyncio.Task[None]] = set()
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
            print_stream_message(message)

    async def _handle_input_requests(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        while True:
            input_request_message = await self.session.stream.recv("input_request")
            # TODO: Make extra kwargs like plain constants
            if (
                input_request_message.extra is not None
                and input_request_message.extra.get("plain")
            ):
                prompt_session = self._plain_session
            else:
                prompt_session = self._prompt_session
            user_input = await prompt_session.prompt_async(handle_sigint=False)
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

    # Be careful editing this function; since we use signal.signal instead of asyncio's
    # add signal handler (which isn't available on Windows), this function can interrupt
    # asyncio coroutines, potentially causing race conditions.
    def _handle_exit(self, sig: int, frame: FrameType | None):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        if (
            self.session.is_stopped
            or self.session.stream.interrupt_lock.locked() is False
        ):
            if self._should_exit:
                logging.debug("Force exiting client...")
                self._force_exit = True
            else:
                logging.debug("Should exit client...")
                self._should_exit = True

        else:
            logging.debug("Sending interrupt to session stream")
            self._create_task(self._send_session_stream_interrupt())

    def _init_signal_handlers(self):
        signal.signal(signal.SIGINT, self._handle_exit)

    async def _startup(self):
        assert self.session is None, "TerminalClient already running"

        self.session = await Session.create(
            self.paths,
            self.exclude_paths,
            self.no_code_map,
            self.diff,
            self.pr_diff,
            self.auto_tokens,
        )
        self.session.start()
        # Logging is setup in session.start()
        logging.debug("Running startup")

        mentat_completer = MentatCompleter()
        self._prompt_session = MentatPromptSession(completer=mentat_completer)

        plain_bindings = KeyBindings()

        @plain_bindings.add("c-c")
        @plain_bindings.add("c-d")
        def _(event: KeyPressEvent):
            if event.current_buffer.text != "":
                event.current_buffer.reset()
            else:
                event.app.exit(result="q")

        self._plain_session = PromptSession[str](
            message=[("class:prompt", ">>> ")],
            style=Style(CONFIG_MANAGER.get().input_style()),
            completer=None,
            key_bindings=plain_bindings,
        )

        self._create_task(mentat_completer.refresh_completions())
        self._create_task(self._cprint_session_stream())
        self._create_task(self._handle_input_requests())

        logging.debug("Completed startup")

    async def _shutdown(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"

        logging.debug("Running shutdown")

        # Stop session
        self.session.stop()
        while not self._force_exit and not self.session.is_stopped:
            await asyncio.sleep(0.01)
        self.session = None
        # logging is shutdown by session stop

        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        while not self._force_exit:
            if all([task.cancelled() for task in self._tasks]):
                break
            await asyncio.sleep(0.01)

    async def _main(self):
        assert isinstance(self.session, Session), "TerminalClient is not running"
        logging.debug("Running main loop")

        while not self._should_exit and not self.session.is_stopped:
            await asyncio.sleep(0.01)

    async def _run(self):
        self._init_signal_handlers()
        await self._startup()
        await self._main()
        await self._shutdown()

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
    parser.add_argument(
        "--auto-tokens",
        "-a",
        type=int,
        default=None,
        help="Maximum number of auto-generated tokens to include in the prompt context",
    )
    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    no_code_map = args.no_code_map
    diff = args.diff
    pr_diff = args.pr_diff
    auto_tokens = args.auto_tokens

    # Expanding paths as soon as possible because some shells such as zsh automatically
    # expand globs and we want to avoid differences in functionality between shells
    terminal_client = TerminalClient(
        expand_paths(paths),
        expand_paths(exclude_paths),
        no_code_map,
        diff,
        pr_diff,
        auto_tokens,
    )
    terminal_client.run()
