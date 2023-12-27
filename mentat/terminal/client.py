import argparse
import asyncio
import logging
import signal
from asyncio import Event
from pathlib import Path
from types import FrameType
from typing import Any, Coroutine, List, Set

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.styles import Style

from mentat.config import config, update_config
from mentat.session import Session
from mentat.session_stream import StreamMessageSource
from mentat.terminal.loading import LoadingHandler
from mentat.terminal.output import print_stream_message
from mentat.terminal.prompt_completer import MentatCompleter
from mentat.terminal.prompt_session import MentatPromptSession

from typing import List
from pathlib import Path

import anyio
import inspect
import typer
from functools import partial, wraps
from typer import Typer

from mentat.utils import dd
from asyncio import run as aiorun

class AsyncTyper(Typer):
    @staticmethod
    def maybe_run_async(decorator, f):
        if inspect.iscoroutinefunction(f):

            @wraps(f)
            def runner(*args, **kwargs):
                return asyncio.run(f(*args, **kwargs))

            decorator(runner)
        else:
            decorator(f)
        return f

    def callback(self, *args, **kwargs):
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    def command(self, *args, **kwargs):
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)


app = AsyncTyper()

class TerminalClient:
    def __init__(
        self,
        cwd: Path = Path.cwd(),
        paths: List[str] = [],
        exclude_paths: List[str] = [],
        ignore_paths: List[str] = [],
        diff: str | None = None,
        pr_diff: str | None = None
    ):
        self.cwd = cwd
        self.paths = [Path(path) for path in paths]
        self.exclude_paths = [Path(path) for path in exclude_paths]
        self.ignore_paths = [Path(path) for path in ignore_paths]
        self.diff = diff
        self.pr_diff = pr_diff
        self.config = config

        self._tasks: Set[asyncio.Task[None]] = set()
        self._should_exit = Event()
        self._stopped = Event()

    def _create_task(self, coro: Coroutine[None, None, Any]):
        """Utility method for running a Task in the background"""

        def task_cleanup(task: asyncio.Task[None]):
            self._tasks.remove(task)

        task = asyncio.create_task(coro)
        task.add_done_callback(task_cleanup)
        self._tasks.add(task)

        return task

    async def _cprint_session_stream(self):
        async for message in self.session.stream.listen():
            print_stream_message(message)

    async def _default_prompt_stream(self):
        self._default_prompt = ""
        async for message in self.session.stream.listen("default_prompt"):
            self._default_prompt += message.data

    async def _handle_loading_messages(self):
        loading_handler = LoadingHandler()
        async for message in self.session.stream.listen("loading"):
            loading_handler.update(message)

    async def _handle_input_requests(self):
        while True:
            input_request_message = await self.session.stream.recv("input_request")
            # TODO: Make extra kwargs like plain constants
            if input_request_message.extra.get("plain"):
                prompt_session = self._plain_session
            else:
                prompt_session = self._prompt_session

            default_prompt = self._default_prompt.strip()
            self._default_prompt = ""

            user_input = await prompt_session.prompt_async(
                handle_sigint=False, default=default_prompt
            )
            if user_input == "q":
                self._should_exit.set()
                return

            self.session.stream.send(
                user_input,
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )

    async def _listen_for_client_exit(self):
        """When the Session shuts down, it will send the client_exit signal for the client to shutdown."""
        await self.session.stream.recv(channel="client_exit")
        asyncio.create_task(self._shutdown())

    async def _listen_for_should_exit(self):
        """This listens for a user event signaling shutdown (like SigInt), and tells the session to shutdown."""
        await self._should_exit.wait()
        self.session.stream.send(
            None, source=StreamMessageSource.CLIENT, channel="session_exit"
        )

    async def _send_session_stream_interrupt(self):
        logging.debug("Sending interrupt to session stream")
        self.session.stream.send(
            "", source=StreamMessageSource.CLIENT, channel="interrupt"
        )

    # Be careful editing this function; since we use signal.signal instead of asyncio's
    # add signal handler (which isn't available on Windows), this function can interrupt
    # asyncio coroutines, potentially causing race conditions.
    def _handle_sig_int(self, sig: int, frame: FrameType | None):
        if (
            # If session is still starting up we want to quit without an error
            not self.session
            or self.session.stream.interrupt_lock.locked() is False
        ):
            if self._should_exit.is_set():
                logging.debug("Force exiting client...")
                exit(0)
            else:
                logging.debug("Should exit client...")
                self._should_exit.set()
        else:
            # We create a task here in order to avoid race conditions
            self._create_task(self._send_session_stream_interrupt())

    def _init_signal_handlers(self):
        signal.signal(signal.SIGINT, self._handle_sig_int)

    async def _run(self):
        self._init_signal_handlers()
        self.session = Session(
            self.cwd,
            self.paths,
            self.exclude_paths,
            self.ignore_paths,
            self.diff,
            self.pr_diff
        )
        self.session.start()

        mentat_completer = MentatCompleter(self.session.stream)
        self._prompt_session = MentatPromptSession(
            completer=mentat_completer,
            style=Style(self.config.ui.input_style),
            enable_suspend=True,
        )

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
            style=Style(self.config.ui.input_style),
            completer=None,
            key_bindings=plain_bindings,
            enable_suspend=True,
        )

        self._create_task(self._cprint_session_stream())
        self._create_task(self._handle_input_requests())
        self._create_task(self._handle_loading_messages())
        self._create_task(self._default_prompt_stream())
        self._create_task(self._listen_for_client_exit())
        self._create_task(self._listen_for_should_exit())

        logging.debug("Completed startup")
        await self._stopped.wait()

    async def _shutdown(self):
        logging.debug("Running shutdown")

        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        self._stopped.set()


@app.command()
async def async_hello(name: str, last_name: str = "") -> None:
    await anyio.sleep(1)
    typer.echo(f"Hello World {name} {last_name}")


@app.command()
def start(paths: List[str] = typer.Argument(...),
          exclude_paths: List[str] = typer.Option([], "--exclude-paths", "-e", help="List of file paths, directory paths, or glob patterns to exclude"),
          ignore_paths: List[str] = typer.Option([], "--ignore-paths", "-g", help="List of file paths, directory paths, or glob patterns to ignore in auto-context"),
          diff: str = typer.Option(None, "--diff", "-d", show_default='HEAD', help="A git tree-ish (e.g. commit, branch, tag) to diff against"),
          pr_diff: str = typer.Option(None, "--pr-diff", "-p", help="A git tree-ish to diff against the latest common ancestor of"),
          cwd: Path = typer.Option(Path.cwd(), "--cwd", help="The current working directory")) -> None:


    # Check if these variables are set and pass them to update_config function as kwargs
    session_config = {'file_exclude_glob_list': []}

    if exclude_paths:
        session_config["file_exclude_glob_list"] = exclude_paths

    update_config(session_config)

    cwd = Path(cwd).expanduser().resolve()

    terminal_client = TerminalClient(
        cwd,
        paths,
        exclude_paths,
        ignore_paths,
        diff,
        pr_diff
    )
    asyncio.run(terminal_client._run())



if __name__ == "__main__":
    typer.run(start())
