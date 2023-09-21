import argparse
import asyncio
import logging
import signal
import traceback
from typing import Coroutine, List, Set
from uuid import UUID

from ipdb import set_trace

from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.terminal.output import cprint, cprint_message
from mentat.terminal.prompt_completer import MentatCompleter
from mentat.terminal.prompt_session import MentatPromptSession

# Move this to the cli file?
setup_logging()

logger = logging.getLogger("mentat.terminal")


class TerminalClient:
    def __init__(self):
        self.engine = Engine()
        self.engine_task: asyncio.Task | None = None

        self.session_id: UUID | None = None

        self._tasks: Set[asyncio.Task] = set()
        self._prompt_session = MentatPromptSession(
            self.engine, message=[("class:prompt", ">>> ")]
        )

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

    async def _session_listen(self):
        if self.session_id is None:
            raise Exception("session_id is NoneType")
        try:
            async for message in self.engine.session_listen(self.session_id):
                cprint_message(message)
                if "type" in message.data:
                    if message.data["type"] == "collect_user_input":
                        self._input_queue.put_nowait(message)
        except Exception as e:
            cprint(f"There was an exception: {e}", color="red")
            traceback.print_exc()

    async def _session_interrupt(self):
        if self.session_id is None:
            raise Exception("session_id is NoneType")
        await self.engine.session_send(
            self.session_id, content="", message_type="interrupt"
        )

    async def handle_user_input(self) -> str:
        if self.session_id is None:
            raise Exception("session_id is NoneType")

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

            await self.engine.session_send(
                self.session_id,
                content=user_input,
                channel=f"default:{input_request_message.id}",
            )

    # FIXME
    def _handle_exit(self):
        print("Terminal client got a signal")
        self._create_task(self._session_interrupt())
        # if self._should_exit:
        #     self._force_exit = True
        # else:
        #     self._should_exit = True

    def _init_signal_handlers(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._handle_exit)
        loop.add_signal_handler(signal.SIGTERM, self._handle_exit)

    async def _startup(self):
        self.engine_task = asyncio.create_task(
            self.engine._run(install_signal_handlers=False)
        )

        def cleanup_engine_task(task):
            # set_trace()
            pass

        self.engine_task.add_done_callback(cleanup_engine_task)

    async def _shutdown(self):
        logger.debug("Shutting Engine down...")
        self.engine._should_exit = True
        assert self.engine_task
        await self.engine_task
        self.engine_task = None

    async def _main(
        self,
        paths: List[str] | None = [],
        exclude_paths: List[str] | None = [],
        no_code_map: bool = False,
    ):
        self.session_id = await self.engine.session_create(
            paths, exclude_paths, no_code_map
        )

        # TODO: shutdown this task properly
        session_listen_task = asyncio.create_task(self._session_listen())

        try:
            await self.handle_user_input()
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
