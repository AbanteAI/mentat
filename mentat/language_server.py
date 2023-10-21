import argparse
import asyncio
import inspect
import logging
import signal
import threading
from typing import Any, Coroutine, Set

import debugpy
from ipdb import set_trace
from lsprotocol.types import EXIT, INITIALIZED
from pygls.protocol import LanguageServerProtocol
from pygls.server import LanguageServer
from typing_extensions import override

from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_stream import StreamMessageSource

setup_logging()

logger = logging.getLogger("mentat:server")


class MentatLanguageServerProtocol(LanguageServerProtocol):
    @override
    def connection_lost(self, exc: Exception):
        if not isinstance(self._server, MentatLanguageServer):
            set_trace()
            super().connection_lost(exc)
        else:
            if self._server._should_exit_on_lost_connection:
                logger.error(
                    "Connection to the client is lost! Shutting down the server"
                )
                if self._server._stop_event:
                    self._server._stop_event.set()
                    self._server._should_exit_event.set()
            else:
                logger.error("Connection to the client is lost! Doing nothing.")


def lsp_feature(name: str):
    def decorator(fn):
        setattr(fn, "lsp_feature", name)
        return fn

    return decorator


class MentatLanguageServer(LanguageServer):
    def __init__(self, should_exit_on_lost_connection: bool = True):
        self._should_exit_on_lost_connection = should_exit_on_lost_connection
        self._should_exit_event = asyncio.Event()

        self._server_task: asyncio.Task | None = None
        super().__init__(
            name="mentat-server",
            version="v0.1",
            loop=asyncio.get_running_loop(),
            protocol_cls=MentatLanguageServerProtocol,
        )
        self._register_features()

    def _register_features(self):
        for name, function in inspect.getmembers(
            MentatLanguageServer, predicate=inspect.isfunction
        ):
            if not function.__qualname__.startswith(MentatLanguageServer.__name__):
                continue
            lsp_method = getattr(self, name, None)
            if lsp_method is None:
                continue
            lsp_feature = getattr(function, "lsp_feature", None)
            if lsp_feature is not None:
                logger.debug(f"registering LSP feature '{lsp_feature}' to {name}")
                set_trace()
                self.feature(lsp_feature)(lsp_method)

                self.lsp.fm.feature(lsp_feature, None)(lsp_method)
                pass

    @property
    def is_serving(self):
        return self._server is not None and self._server.is_serving

    @property
    def should_sys_exit(self):
        return self._should_exit_event.is_set()

    @override
    def start_tcp(self, host: str, port: int) -> None:
        """Starts TCP server in a background asyncio.Task"""

        async def _start():
            logger.info("Starting TCP server on %s:%s", host, port)
            self._stop_event = threading.Event()
            self._server = await self.loop.create_server(self.lsp, host, port)
            try:
                await self._server.serve_forever()
            except (KeyboardInterrupt, SystemExit):
                set_trace()
                pass
            finally:
                if self._server:
                    await self.shutdown()

        def _start_cleanup(_: asyncio.Task):
            self._server_task = None

        self._server_task = asyncio.create_task(_start())
        self._server_task.add_done_callback(_start_cleanup)

    @override
    async def shutdown(self):
        """Shutdown server."""
        logger.info("Shutting down the server")

        if self._stop_event is not None:
            self._stop_event.set()

        if self._thread_pool:
            self._thread_pool.terminate()
            self._thread_pool.join()

        if self._thread_pool_executor:
            self._thread_pool_executor.shutdown()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @lsp_feature(INITIALIZED)
    async def on_initalized(params: Any):
        # breakpoint()
        print("INITALIZED")

    @lsp_feature("mentat/getInput")
    async def get_input(self, params):
        set_trace()
        pass

    @lsp_feature("mentat/createSession")
    async def create_session(self, params):
        set_trace()
        pass
        # print("mentat/createSession")
        # server._create_task(server._handle_session_output())
        # server._create_task(server._handle_input_requests())

    @lsp_feature("mentat/streamSession")
    async def stream_session(self, params):
        set_trace()
        pass


class Server:
    def __init__(
        self, language_server_host: str = "127.0.0.1", language_server_port: int = 7798
    ):
        self.language_server_host = language_server_host
        self.language_server_port = language_server_port

        self.language_server: MentatLanguageServer | None = None
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

    async def _handle_session_output(self):
        assert isinstance(self.language_server, LanguageServer)
        assert isinstance(self.session, Session)
        async for message in self.session.stream.listen():
            self.language_server.send_notification(
                method="mentat/streamSession", params=message.model_dump(mode="json")
            )

    async def _handle_input_requests(self):
        assert isinstance(self.language_server, LanguageServer)
        assert isinstance(self.session, Session)
        while True:
            input_request_message = await self.session.stream.recv("input_request")

            logger.debug("sending input request to client")
            language_client_res = await self.language_server.lsp.send_request_async(
                method="mentat/getInput",
                params=input_request_message.model_dump(mode="json"),
            )
            logger.debug(
                "Got input response:", language_client_res[0]["data"]["content"]
            )

            await self.session.stream.send(
                data=language_client_res[0]["data"]["content"],
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{str(input_request_message.id)}",
            )

    def _handle_exit(self):
        if self._should_exit:
            logger.debug("Force exiting client...")
            self._force_exit = True
        else:
            logger.debug("Should exit client...")
            self._should_exit = True

    def _init_signal_handlers(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._handle_exit)

    async def _startup(self):
        logger.debug("Running startup")
        assert self.session is None
        assert self.language_server is None

        self.session = await Session.create(paths=[], exclude_paths=[])
        self.session.start()

        self.language_server = MentatLanguageServer()
        self.language_server.start_tcp(
            host=self.language_server_host, port=self.language_server_port
        )

        logger.debug("Finished startup")

    async def _shutdown(self):
        logger.debug("Running shutdown")
        assert isinstance(self.session, Session)
        assert isinstance(self.language_server, MentatLanguageServer)

        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        while not self._force_exit:
            if all([task.cancelled() for task in self._tasks]):
                break
            await asyncio.sleep(0.01)

        # Stop session
        session_stop_task = self.session.stop()
        if isinstance(session_stop_task, asyncio.Task):
            await session_stop_task
        self.session = None

        # Stop language server
        await self.language_server.shutdown()

        logger.debug("Finished shutdown")

    async def _main(self):
        logger.debug("Running main loop")
        assert isinstance(self.session, Session)
        assert isinstance(self.language_server, MentatLanguageServer)

        while not self._should_exit and not self.language_server.should_sys_exit:
            await asyncio.sleep(0.01)

        logger.debug("Finished main loop")

    async def _run(self):
        self._init_signal_handlers()
        await self._startup()
        await self._main()
        await self._shutdown()

    def run(self):
        # debugpy.listen(("localhost", 5678))
        # print("Waiting for client to connect to debugpy")
        # debugpy.wait_for_client()
        asyncio.run(self._run())


def run_cli():
    parser = argparse.ArgumentParser(description="Start the Mentat Server")
    parser.add_argument("--host", default="127.0.0.1", type=str)
    parser.add_argument("--port", default=7798, type=int)
    args = parser.parse_args()

    server = Server(language_server_host=args.host, language_server_port=args.port)
    server.run()
