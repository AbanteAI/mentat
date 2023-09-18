import asyncio
import logging
import signal
import sys
from typing import Any, Dict, Iterable, List, Set
from uuid import UUID

from ipdb import set_trace

from mentat.llm_api import CostTracker

from .config_manager import ConfigManager
from .git_handler import get_shared_git_root_for_paths
from .rpc import RpcServer
from .session import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mentat.engine")


class Engine:
    """A global process and task manager.

    A client (Terminal, VSCode extension, NeoVim plugin, etc.) will use an `Engine`
    instance for any Mentat functionality.
    """

    def __init__(self, with_rpc_server: bool = False):
        self.rpc_server = RpcServer() if with_rpc_server else None
        self.sessions: Dict[UUID, Session] = {}

        self._should_exit = False
        self._force_exit = False
        self._tasks: Set[asyncio.Task] = set()

    ### rpc-exposed methods (terminal client can call these directly)

    async def on_connect(self):
        """Sets up an RPC connection with a client"""
        ...

    async def disconnect(self):
        """Closes an RPC connection with a client"""
        ...

    async def restart(self):
        """Restart the MentatEngine and RPC server"""
        ...

    async def shutdown(self):
        """Shutdown the MentatEngine and RPC server"""
        ...

    # Session

    async def session_create(
        self,
        paths: List[str] | None = [],
        exclude_paths: List[str] | None = [],
        no_code_map: bool = False,
    ) -> UUID:
        session = Session(paths, exclude_paths, no_code_map)
        session.start()
        self.sessions[session.id] = session

        return session.id

    async def session_exists(self, session_id: UUID):
        return True if session_id in self.sessions else False

    async def session_listen(self, session_id: UUID):
        if session_id not in self.sessions:
            raise Exception(f"Session {session_id} does not exist")
        session = self.sessions[session_id]
        async for message in session.session_conversation.listen():
            yield message

    async def session_send(
        self, session_id: UUID, content: Any, channel: str = "default", **kwargs
    ):
        if session_id not in self.sessions:
            raise Exception(f"Session {session_id} does not exist")
        session = self.sessions[session_id]
        message = await session.session_conversation.send_message(
            source="client", data=dict(content=content, **kwargs), channel=channel
        )

        return message.id

    async def session_recv(self, session_id: UUID):
        if session_id not in self.sessions:
            raise Exception(f"Session {session_id} does not exist")

    async def get_session_code_context(self, session_id: UUID):
        if session_id not in self.sessions:
            set_trace()
            raise Exception(f"Session {session_id} does not exist")
        session = self.sessions[session_id]
        code_context_file_paths = list(session.code_context.files.keys())

        return code_context_file_paths

    async def create_conversation_message(self):
        ...

    async def get_conversation_cost(self):
        ...

    # Completions

    async def get_conversation_completions(self):
        ...

    # Commands

    async def get_commands(self):
        ...

    async def run_command(self, command: str):
        ...

    ### lifecycle methods

    async def heartbeat(self):
        while True:
            logger.debug("heartbeat")
            await asyncio.sleep(3)

    def _handle_exit(self):
        print("got a signal")
        if self._should_exit:
            self._force_exit = True
        else:
            self._should_exit = True

    def _init_signal_handlers(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._handle_exit)
        loop.add_signal_handler(signal.SIGTERM, self._handle_exit)

    async def _startup(self):
        logger.debug("Starting Engine...")
        heahtheck_task = asyncio.create_task(self.heartbeat())
        self._tasks.add(heahtheck_task)

    async def _main_loop(self):
        logger.debug("Running Engine...")

        counter = 0
        while not self._should_exit:
            counter += 1
            counter = counter % 86400
            await asyncio.sleep(0.1)

    async def _shutdown(self):
        logger.debug("Shutting Engine down...")

        for task in self._tasks:
            task.cancel()
        logger.debug("Waiting for Jobs to finish. (CTRL+C to force quit)")
        while not self._force_exit:
            if all([task.cancelled() for task in self._tasks]):
                break
            await asyncio.sleep(0.1)

        if self._force_exit:
            logger.debug("Force exiting.")

        logger.debug("Engine has stopped")

    async def _run(self, install_signal_handlers: bool = True):
        try:
            if install_signal_handlers:
                self._init_signal_handlers()
            await self._startup()
            await self._main_loop()
            await self._shutdown()
        except:
            set_trace()
            pass

    def run(self, install_signal_handlers: bool = True):
        asyncio.run(self._run(install_signal_handlers=install_signal_handlers))


def run_cli():
    mentat_engine = Engine()
    mentat_engine.run()
