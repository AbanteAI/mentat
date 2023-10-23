import argparse
import asyncio
import inspect
import json
import logging
import signal
import threading
import urllib.parse as urlparse
from functools import partial
from pathlib import Path
from typing import Any

import debugpy
import lsprotocol.types as lsp
from pygls.protocol import LanguageServerProtocol
from pygls.server import LanguageServer
from typing_extensions import override

from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_manager import SessionManager
from mentat.session_stream import StreamMessageSource

setup_logging()

logger = logging.getLogger("mentat:server")


class MentatLanguageServerProtocol(LanguageServerProtocol):
    @override
    def connection_lost(self, exc: Exception):
        """Shutdown the LanguageServer on lost client connection"""
        if not isinstance(self._server, MentatLanguageServer):
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
    def __init__(
        self,
        session_manager: SessionManager,
        should_exit_on_lost_connection: bool = True,
    ):
        self.session_manager = session_manager

        self.selected_file: Path | None = None

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
                # NOTE: this is super hacky
                self.feature(lsp_feature)(partial(lsp_method))

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
                logger.debug("Got an exception")
                pass
            finally:
                logger.debug("Killing server")
                if self._server:
                    await self.shutdown()

        def _start_cleanup(_: asyncio.Task):
            self._server_task = None

        logger.debug("Creating start_tcp task")

        self._server_task = asyncio.create_task(_start())
        self._server_task.add_done_callback(_start_cleanup)

        logger.debug("Created start_tcp task")

    @override
    async def shutdown(self):
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

    @lsp_feature(lsp.TEXT_DOCUMENT_DID_OPEN)
    async def handle_text_document_did_open(
        self, params: lsp.DidOpenTextDocumentParams
    ):
        parsed_uri = urlparse.urlparse(params.text_document.uri)
        if parsed_uri.scheme == "file":
            file_path = Path(parsed_uri.path)
        elif parsed_uri.scheme == "git":
            decoded_query_params = json.loads(urlparse.unquote(parsed_uri.query))
            file_path = Path(decoded_query_params["path"])
        else:
            logger.warning(f"Unhandled file uri scheme '{parsed_uri.scheme}'")
            return

        if file_path == self.selected_file:
            return
        self.selected_file = file_path

        logger.debug(f"Opened: {self.selected_file}")

    @lsp_feature("mentat/createSession")
    async def create_session(self, params):
        async def handle_session_output(session: Session):
            async for message in session.stream.listen():
                self.send_notification(
                    method="mentat/streamSession",
                    params=message.model_dump(mode="json"),
                )

        async def handle_input_request(session: Session):
            while True:
                input_request_message = await session.stream.recv("input_request")

                logger.debug("sending input request to client")
                language_client_res = await self.lsp.send_request_async(
                    method="mentat/getInput",
                    params=input_request_message.model_dump(mode="json"),
                )

                logger.debug(
                    f"Got input response: {language_client_res[0]['data']['content']}"
                )
                if self.selected_file is not None:
                    session.code_context.set_paths([self.selected_file], [])

                session.stream.send(
                    data=language_client_res[0]["data"]["content"],
                    source=StreamMessageSource.CLIENT,
                    channel=f"input_request:{str(input_request_message.id)}",
                )

        self.session_manager.create_session(
            on_output=handle_session_output, on_input_request=handle_input_request
        )


class Server:
    def __init__(
        self,
        language_server_host: str = "127.0.0.1",
        language_server_port: int = 7798,
        debugpy: bool = False,
        debugpy_host: str = "localhost",
        debugpy_port: int = 5678,
    ):
        self.language_server_host = language_server_host
        self.language_server_port = language_server_port
        self.debugpy = debugpy
        self.debugpy_host = debugpy_host
        self.debugpy_port = debugpy_port

        self.language_server: MentatLanguageServer | None = None
        self.session_manager = SessionManager()

        self._should_exit = False
        self._force_exit = False

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
        assert self.language_server is None

        self.language_server = MentatLanguageServer(
            session_manager=self.session_manager, should_exit_on_lost_connection=False
        )
        self.language_server.start_tcp(
            host=self.language_server_host, port=self.language_server_port
        )

        logger.debug("Finished startup")

    async def _shutdown(self):
        logger.debug("Running shutdown")
        assert isinstance(self.language_server, MentatLanguageServer)

        # Stop Session manager
        await self.session_manager.shutdown()

        # Stop language server
        await self.language_server.shutdown()

        logger.debug("Finished shutdown")

    async def _main(self):
        logger.debug("Running main loop")
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
        if self.debugpy:
            debugpy.listen((self.debugpy_host, self.debugpy_port))
            logger.debug("Waiting for client to connect to debugpy")
            debugpy.wait_for_client()
        asyncio.run(self._run())


def run_cli():
    parser = argparse.ArgumentParser(description="Start the Mentat Server")
    parser.add_argument("--host", default="127.0.0.1", type=str)
    parser.add_argument("--port", default=7798, type=int)
    args = parser.parse_args()

    server = Server(
        language_server_host=args.host, language_server_port=args.port, debugpy=False
    )
    server.run()


if __name__ == "__main__":
    run_cli()
