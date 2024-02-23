import argparse
import asyncio
import json
import logging
from pathlib import Path

from mentat.session import Session
from mentat.session_stream import StreamMessage, StreamMessageSource

HOST = "127.0.0.1"
PORT = "7798"


# TODO: Look into if we want to use HTTP
class MentatServer:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        self.stopped = asyncio.Event()
        self.session = Session(self.cwd)

    async def _client_listener(self, reader: asyncio.StreamReader):
        while not self.stopped.is_set():
            message: StreamMessage = json.loads(await reader.readuntil("\n".encode()))
            self.session.stream.send_stream_message(message)

    async def _client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        listener_task = asyncio.create_task(self._client_listener(reader))
        async for message in self.session.stream.universal_listen():
            if message.source == StreamMessageSource.SERVER:
                message_json = json.dumps(message) + "\n"
                writer.write(message_json.encode())
            elif message.channel == "session_exit":
                self.stopped.set()
                try:
                    listener_task.cancel()
                except asyncio.CancelledError:
                    pass
            break

    async def run(self):
        self.session.start()
        logging.debug("Completed startup")

        server = await asyncio.start_server(
            self._client_connected, host=HOST, port=PORT
        )
        await self.stopped.wait()
        server.close()


async def run(args: argparse.Namespace):
    cwd = Path(args.cwd).expanduser().resolve()
    mentat_server = MentatServer(cwd)
    await mentat_server.run()


def main():
    parser = argparse.ArgumentParser(
        description="Run conversation with command line args",
    )
    parser.add_argument("cwd", help="The working directory for the server to run in")
    args = parser.parse_args()
    asyncio.run(run(args))
