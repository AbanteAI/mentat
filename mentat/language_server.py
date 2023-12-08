import asyncio
import logging
import threading

import lsprotocol.types as lsp
from pygls.server import LanguageServer

from mentat import __version__
from mentat.logging_config import setup_logging

setup_logging()

logger = logging.getLogger("mentat:server")


class MentatLanguageServer(LanguageServer):
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
            # loop=asyncio.get_running_loop()
            # loop=loop,
        )

        self._should_exit_event = asyncio.Event()

        self._server: asyncio.Server | None = None
        self._server_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None

    @property
    def is_serving(self):
        return self._server is not None and self._server.is_serving

    @property
    def should_sys_exit(self):
        return self._should_exit_event.is_set()

    async def _serve_tcp(self) -> None:
        logger.info(f"Starting TCP server on {self.host}:{self.port}")
        self._stop_event = threading.Event()
        self._server = await self.loop.create_server(self.lsp, self.host, self.port)
        try:
            await self._server.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            logger.debug("Got an exception")
            pass
        finally:
            logger.debug("Killing server")
            if self._server:
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


server = MentatLanguageServer(host="127.0.0.1", port=7798)


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
async def handle_text_document_did_open(params: lsp.DidOpenTextDocumentParams):
    print("Got params:", params)


def main():
    server.loop.run_until_complete(server.start())


if __name__ == "__main__":
    main()
