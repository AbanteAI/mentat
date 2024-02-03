from __future__ import annotations

import argparse
import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Literal, NamedTuple
from uuid import UUID

import pygls.protocol
import pygls.server
from lsprotocol import types as lsp
from pydantic import BaseModel
from typing_extensions import override

from mentat import __version__
from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.session_stream import StreamMessageSource

setup_logging()

logger = logging.getLogger("mentat:language-server")


class LanguageServerMessage(BaseModel):
    type: Literal["notification", "request", "command"]
    method: Literal["mentat/serverMessage", "mentat/clientMessage", "mentat/inputRequest"]
    data: Any


class LanguageServerProtocol(pygls.protocol.LanguageServerProtocol):
    _server: LanguageServer

    @override
    def connection_lost(self, _: Exception | None):  # pyright: ignore[reportIncompatibleMethodOverride]
        """Shutdown the LanguageServer on lost client connection"""
        if self._server.exit_on_lost_connection and not self._server.is_stopped:
            logger.error("Connection to the client is lost! Shutting down the server")
            self._server.stop()
        else:
            logger.error("Connection to the client is lost! Doing nothing.")


class LanguageServer(pygls.server.LanguageServer):
    def __init__(
        self,
        host: str,
        port: int,
        exit_on_lost_connection: bool = True,
    ):
        self.host = host
        self.port = port
        self.exit_on_lost_connection = exit_on_lost_connection

        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            name="mentat",
            version=f"v{__version__}",
            protocol_cls=LanguageServerProtocol,
        )

        self._server: asyncio.Server | None = None
        self._server_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None

        self.cwd: Path | None = None
        self.session: Session | None = None
        self.handle_session_stream_task: asyncio.Task[None] | None = None
        self.handle_input_requests_task: asyncio.Task[None] | None = None

        self.session_input_request_id: UUID | None = None

    @property
    def is_serving(self):
        return self._server is not None and self._server.is_serving

    @property
    def is_stopping(self):
        return self._stop_task is not None and not self._stop_task.done()

    @property
    def is_stopped(self):
        return not self.is_serving and not self.is_stopping

    async def _serve_tcp(self) -> None:
        logger.info(f"Starting TCP server on {self.host}:{self.port}")
        self._stop_event = threading.Event()
        self._server = await self.loop.create_server(self.lsp, self.host, self.port)
        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:
            pass
        except (KeyboardInterrupt, SystemExit):
            logger.debug("Got an exception")
            pass
        finally:
            if self.is_serving and not self.is_stopping:
                logger.debug("Killing server")
                await self.stop()

    def start(self) -> asyncio.Task[None]:
        """Starts TCP server in a background asyncio.Task"""

        def callback(_: asyncio.Task[None]):
            self._server_task = None

        self._server_task = self.loop.create_task(self._serve_tcp())
        self._server_task.add_done_callback(callback)

        return self._server_task

    async def _stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

        if self._thread_pool:
            # NOTE: might be blocking the async event loop
            self._thread_pool.terminate()
            self._thread_pool.join()

        if self._thread_pool_executor:
            # NOTE: might be blocking the async event loop
            self._thread_pool_executor.shutdown()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def stop(self) -> asyncio.Task[None]:
        logger.info("Stopping the language server")

        def callback(_: asyncio.Task[None]):
            logger.info("The language server has stopped")
            self._stop_task = None

        self._stop_task = self.loop.create_task(self._stop())
        self._stop_task.add_done_callback(callback)

        return self._stop_task


server = LanguageServer(host="127.0.0.1", port=7798, exit_on_lost_connection=False)


@server.feature(lsp.INITIALIZE)
async def initialize(ls: LanguageServer, params: lsp.InitializeParams):
    if params.root_path is None:
        logger.debug("No root path provided, using home directory")
        ls.cwd = Path.home()
    else:
        ls.cwd = Path(params.root_path)


@server.feature("mentat/createSession")
async def create_session(ls: LanguageServer, params: lsp.InitializeParams):
    assert ls.cwd is not None

    ls.session = Session(cwd=ls.cwd)
    ls.session.start()

    async def handle_session_stream():
        if ls.session is None:
            return
        async for message in ls.session.stream.listen():
            logger.debug(f"Received Session Message: {message.data} {message.extra}")
            ls_message = LanguageServerMessage(type="notification", method="mentat/serverMessage", data=message)
            ls.send_notification("mentat/serverMessage", ls_message.model_dump(mode="json"))

    async def handle_input_requests():
        if ls.session is None:
            return
        while True:
            input_request_message = await ls.session.stream.recv("input_request")
            print("Got input request:", input_request_message)
            ls.session_input_request_id = input_request_message.id
            ls_message = LanguageServerMessage(
                type="notification",
                method="mentat/inputRequest",
                data=input_request_message,
            )
            ls.send_notification("mentat/inputRequest", ls_message.model_dump(mode="json"))

    ls.handle_session_stream_task = asyncio.create_task(handle_session_stream())
    ls.handle_input_requests_task = asyncio.create_task(handle_input_requests())

    print("Waiting for input request")
    input_request_message = await ls.session.stream.recv("input_request")
    ls.session_input_request_id = input_request_message.id

    print("Got input request:", input_request_message)


@server.feature(lsp.SHUTDOWN)
async def shutdown(ls: LanguageServer):
    if ls.session is None:
        return
    ls.session.stream.send(None, channel="session_exit")


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
async def handle_text_document_did_open(ls: LanguageServer, params: lsp.DidOpenTextDocumentParams):
    if ls.session is None:
        return
    # print("Got params:", params)


class Message(NamedTuple):
    data: Any


@server.feature("mentat/clientMessage")
async def handle_client_message(ls: LanguageServer, message: Any):
    if ls.session is None:
        return
    if ls.session_input_request_id is None:
        print("No input request id")

    print("Got:", message)

    ls.session.stream.send(
        message.data,
        source=StreamMessageSource.CLIENT,
        channel=f"input_request:{ls.session_input_request_id}",
    )


@server.feature("mentat/sendChat")
async def send_chat(ls: LanguageServer, chat: Message):
    if ls.session is None:
        return
    ls.session.stream.send(chat.data, channel="chat")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Wait for debugger attach")
    args = parser.parse_args()

    if args.debug:
        import debugpy  # pyright: ignore[reportMissingImports, reportMissingTypeStubs]

        print("Waiting for debugger attach")
        debugpy.listen(("localhost", 5678))  # pyright: ignore
        debugpy.wait_for_client()  # pyright: ignore
        print("Debugger attached!")

    server.loop.run_until_complete(server.start())


if __name__ == "__main__":
    main()
