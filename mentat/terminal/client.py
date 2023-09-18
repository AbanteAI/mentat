import argparse
import asyncio
import logging
import signal
import traceback
from typing import Iterable, Set

from ipdb import set_trace

from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_conversation import SessionConversation
from mentat.terminal.output import cprint, cprint_message
from mentat.terminal.prompt_session import MentatPromptSession

# Move this to the cli file?
setup_logging()

logger = logging.getLogger("mentat.terminal")


class TerminalClient:
    def __init__(self):
        self.engine = Engine()
        self.engine_task: asyncio.Task | None = None
        self.session: Session | None = None

        self._tasks: Set[asyncio.Task] = set()

        self._prompt_session = MentatPromptSession(
            self.engine,
            message=[("class:prompt", ">>> ")],
        )

        # NOTE: should input requests be 'stackable'? Should there only be 1 input request at a time?
        self._input_queue = asyncio.Queue()

    async def stream_conversation(self):
        if not isinstance(self.session, Session):
            raise Exception("Session does not exist")

        try:
            async for message in self.session.session_conversation.listen():
                cprint_message(message)

                if "type" in message.data:
                    if message.data["type"] == "collect_user_input":
                        self._input_queue.put_nowait(message)
        except Exception as e:
            cprint(f"There was an exception: {e}", color="red")
            traceback.print_exc()

    def send_interrupt(self):
        if not isinstance(self.session, Session):
            raise Exception("Session does not exist")

        async def _send_interrupt():
            if not isinstance(self.session, Session):
                raise Exception("Session does not exist")
            await self.session.session_conversation.send_message(
                source="client", data=dict(message_type="interrupt")
            )

        def _send_interrupt_cleanup(task: asyncio.Task):
            self._tasks.remove(task)

        send_interrupt_task = asyncio.create_task(_send_interrupt())
        send_interrupt_task.add_done_callback(_send_interrupt_cleanup)
        self._tasks.add(send_interrupt_task)

    async def handle_user_input(self) -> str:
        if not isinstance(self.session, Session):
            raise Exception("Session does not exist")

        while True:
            input_request_message = await self._input_queue.get()

            user_input = await self._prompt_session.prompt_async(handle_sigint=False)
            if user_input == "q":
                raise KeyboardInterrupt

            await self.session.session_conversation.send_message(
                source="client",
                data={"content": user_input},
                channel=f"default:{input_request_message.id}",
            )

    def _handle_exit(self):
        self.send_interrupt()
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

    async def _shutdown(self):
        logger.debug("Shutting Engine down...")
        self.engine._should_exit = True
        assert self.engine_task
        await self.engine_task
        self.engine_task = None

    async def _main(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
    ):
        self.session = await self.engine.create_session(
            paths, exclude_paths, no_code_map
        )
        stream_conversation_task = asyncio.create_task(self.stream_conversation())
        try:
            await self.handle_user_input()
        except KeyboardInterrupt:
            cprint("KeyboardInterrupt", color="yellow")

    async def _run(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
    ):
        self._init_signal_handlers()
        await self._startup()
        await self._main(paths, exclude_paths, no_code_map)
        await self._shutdown()

    def run(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        no_code_map: bool,
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
