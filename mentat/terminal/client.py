from __future__ import annotations

import argparse
import asyncio
import logging
from asyncio import Event
from pathlib import Path
from typing import Any, Coroutine, List, Set

from textual.app import AutopilotCallbackType

from mentat.code_context import ContextStreamMessage
from mentat.config import Config
from mentat.session import Session
from mentat.session_stream import StreamMessageSource
from mentat.terminal.terminal_app import TerminalApp


class TerminalClient:
    def __init__(
        self,
        cwd: Path = Path.cwd(),
        paths: List[str] = [],
        exclude_paths: List[str] = [],
        ignore_paths: List[str] = [],
        diff: str | None = None,
        pr_diff: str | None = None,
        config: Config = Config(),
        # Used for testing
        headless: bool = False,
        auto_pilot: AutopilotCallbackType | None = None,
    ):
        self.cwd = cwd
        self.paths = [Path(path) for path in paths]
        self.exclude_paths = [Path(path) for path in exclude_paths]
        self.ignore_paths = [Path(path) for path in ignore_paths]
        self.diff = diff
        self.pr_diff = pr_diff
        self.config = config
        self.headless = headless
        self.auto_pilot = auto_pilot

        self._tasks: Set[asyncio.Task[None]] = set()
        self._should_exit = Event()
        self._stopped = Event()

    def _create_task(self, coro: Coroutine[None, None, Any]):
        """Utility method for running a Task in the background"""

        def task_cleanup(task: asyncio.Task[None]):
            if task.exception() is not None:
                self.session.stream.send(
                    f"Error in task {task.get_coro()}: {str(task.exception())}",
                    style="error",
                )
                self._should_exit.set()
            self._tasks.remove(task)

        task = asyncio.create_task(coro)
        task.add_done_callback(task_cleanup)
        self._tasks.add(task)

        return task

    async def _run_terminal_app(self):
        self.app = TerminalApp(self)
        await self.app.run_async(headless=self.headless, auto_pilot=self.auto_pilot)
        self._should_exit.set()
        asyncio.create_task(self._shutdown())

    async def _default_channel_stream(self):
        async for message in self.session.stream.listen():
            self.app.display_stream_message(message)

    async def _default_prompt_stream(self):
        self._default_prompt = ""
        async for message in self.session.stream.listen("default_prompt"):
            self._default_prompt += message.data

    async def _listen_for_context_updates(self):
        async for message in self.session.stream.listen("context_update"):
            data: ContextStreamMessage = message.data
            (
                cwd,
                diff_context_display,
                auto_context_tokens,
                features,
                git_diff_paths,
                git_untracked_paths,
                total_tokens,
                total_cost,
            ) = (
                Path(data["cwd"]),
                data["diff_context_display"],
                data["auto_context_tokens"],
                data["features"],
                set(Path(path) for path in data["git_diff_paths"]),
                set(Path(path) for path in data["git_untracked_paths"]),
                data["total_tokens"],
                data["total_cost"],
            )
            self.app.update_context(
                cwd,
                diff_context_display,
                auto_context_tokens,
                features,
                git_diff_paths,
                git_untracked_paths,
                total_tokens,
                total_cost,
            )

    async def _handle_loading_messages(self):
        async for message in self.session.stream.listen("loading"):
            if message.extra.get("terminate", False):
                self.app.end_loading()
            else:
                self.app.start_loading()

    async def _handle_input_requests(self):
        while True:
            input_request_message = await self.session.stream.recv("input_request")

            default_prompt = self._default_prompt.strip()
            self._default_prompt = ""

            command_autocomplete = input_request_message.extra.get("command_autocomplete", False)

            user_input = await self.app.get_user_input(
                default_prompt=default_prompt,
                command_autocomplete=command_autocomplete,
            )

            self.session.stream.send(
                user_input,
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )

    async def _listen_for_session_stopped(self):
        await self.session.stream.recv(channel="session_stopped")
        self.app.disable_app()

    async def _listen_for_client_exit(self):
        await self.session.stream.recv(channel="client_exit")
        asyncio.create_task(self._shutdown())

    async def _listen_for_should_exit(self):
        """
        This listens for a user event signaling session shutdown (like an error), and tells the session to shutdown.
        Does *NOT* shut down the client, only disables it.
        """
        await self._should_exit.wait()
        self.session.stream.send(None, source=StreamMessageSource.CLIENT, channel="session_exit")

    def send_interrupt(self):
        if (
            # If session is still starting up we want to quit without an error
            not self.session or self.session.stream.is_interrupt_locked() is False or self.session.stopped.is_set()
        ):
            if self._should_exit.is_set():
                logging.debug("Force exiting client...")
                exit(0)
            else:
                logging.debug("Should exit client...")
                asyncio.create_task(self._shutdown())
                self._should_exit.set()
        else:
            logging.debug("Sending interrupt to session stream")
            self.session.stream.send(None, source=StreamMessageSource.CLIENT, channel="interrupt")

    async def _run(self):
        self.session = Session(
            self.cwd,
            self.paths,
            self.exclude_paths,
            self.ignore_paths,
            self.diff,
            self.pr_diff,
            self.config,
        )
        self.session.start()

        self._create_task(self._run_terminal_app())
        self._create_task(self._default_channel_stream())
        self._create_task(self._handle_input_requests())
        self._create_task(self._listen_for_context_updates())
        self._create_task(self._handle_loading_messages())
        self._create_task(self._default_prompt_stream())
        self._create_task(self._listen_for_client_exit())
        self._create_task(self._listen_for_session_stopped())
        self._create_task(self._listen_for_should_exit())

        logging.debug("Completed startup")
        await self._stopped.wait()

    async def _shutdown(self):
        logging.debug("Running shutdown")
        await self.session.stopped.wait()

        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        self._stopped.set()

    def run(self):
        asyncio.run(self._run())


def get_parser():
    parser = argparse.ArgumentParser(description="Run conversation with command line args")
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
        "--ignore",
        "-g",
        nargs="*",
        default=[],
        help=("List of file paths, directory paths, or glob patterns to ignore in" " auto-context"),
    )
    parser.add_argument(
        "--diff",
        "-d",
        nargs="?",
        type=str,
        default=None,
        const="HEAD",
        help="A git tree-ish (e.g. commit, branch, tag) to diff against",
    )
    parser.add_argument(
        "--pr-diff",
        "-p",
        type=str,
        default=None,
        help="A git tree-ish to diff against the latest common ancestor of",
    )
    parser.add_argument("--cwd", default=Path.cwd(), help="The current working directory")
    Config.add_fields_to_argparse(parser)
    return parser


def run_cli():
    parser = get_parser()

    args = parser.parse_args()

    cwd = Path(args.cwd).expanduser().resolve()
    paths = args.paths
    exclude_paths = args.exclude
    ignore_paths = args.ignore
    diff = args.diff
    pr_diff = args.pr_diff

    config = Config.create(cwd, args)

    terminal_client = TerminalClient(
        cwd,
        paths,
        exclude_paths,
        ignore_paths,
        diff,
        pr_diff,
        config,
    )
    terminal_client.run()
