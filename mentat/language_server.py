import asyncio
import logging
import signal
from typing import Any, Coroutine, Set
from uuid import uuid4

from ipdb import set_trace  # pyright: ignore
from lsprotocol.types import EXIT
from pygls.protocol import LanguageServerProtocol, lsp_method
from pygls.server import LanguageServer
from typing_extensions import override

from mentat.session import Session
from mentat.session_stream import StreamMessageSource

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# stream_handler = logging.StreamHandler(sys.stdout)
# # stream_handler.setLevel(logging.DEBUG)
# formatter = logging.Formatter("%(asctime)s - %(message)s")
# stream_handler.setFormatter(formatter)
# logger.addHandler(stream_handler)


class MentatLanguageServerProtocol(LanguageServerProtocol):
    @override
    def connection_lost(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, _: Any
    ):
        logger.error("Connection to the client is lost!")

    @lsp_method(EXIT)
    @override
    def lsp_exit(self, *_: Any) -> None:
        """Stops the server process."""
        if self.transport is not None:
            self.transport.close()


class Server:
    def __init__(self):
        self.language_server = LanguageServer(
            name="mentat-server",
            version="v0.1",
            protocol_cls=MentatLanguageServerProtocol,
        )
        self.language_server_server: asyncio.Server | None = None

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

    async def _handle_input_requests(self):
        assert isinstance(self.language_server_server, asyncio.Server)
        assert isinstance(self.session, Session)
        while True:
            await asyncio.sleep(5)
            print("Sending notification")
            self.language_server.send_notification(
                method="mentat/inputRequest",
                params={"input_request_message_id": str(uuid4())},
            )

            # input_request_message = await self.session.stream.recv("input_request")
            #
            # self.language_server.send_notification(method="mentat/inputRequest", params={"input_request_message_id": input_request_message.id})

            # user_input = await prompt_session.prompt_async(handle_sigint=False)
            # assert isinstance(user_input, str)
            #
            # await self.session.stream.send(
            #     user_input,
            #     source=StreamMessageSource.CLIENT,
            #     channel=f"input_request:{input_request_message.id}",
            # )

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
        assert self.language_server_server is None
        assert self.session is None

        logger.debug("Running startup")

        self.language_server_server = await asyncio.get_running_loop().create_server(
            self.language_server.lsp, "127.0.0.1", 7798
        )
        self.session = await Session.create([], [])
        self.session.start()

        self._create_task(self._handle_input_requests())

    async def _shutdown(self):
        assert isinstance(self.language_server_server, asyncio.Server)
        assert isinstance(self.session, Session)

        logger.debug("Running shutdown")

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
        self.language_server_server.close()
        await self.language_server_server.wait_closed()
        self.language_server_server = None

    async def _main(self):
        logger.debug("Running main loop")
        while not self._should_exit:
            await asyncio.sleep(0.01)

    async def _run(self, host: str, port: int):
        self._init_signal_handlers()
        await self._startup()
        await self._main()
        await self._shutdown()

    def run(self, host: str = "127.0.0.1", port: int = 7798):
        asyncio.run(self._run(host=host, port=port))


server = Server()


@server.language_server.feature("mentat/chatMessage")
async def get_chat_message(params: Any):
    print("Got: ", params)

    if server.session is None:
        print("Session is NoneType")
        return

    # await server.session.stream.send(
    #     params.content,
    #     source=StreamMessageSource.CLIENT,
    #     channel=f"input_request:{input_request_message.id}",
    # )
    #
    # server.language_server.send_notification(method="mentat/chatMessageInput", params=)


if __name__ == "__main__":
    print("starting Mentat Server")
    server.run()