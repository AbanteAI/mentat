import argparse
import asyncio
import logging
import sys
from asyncio import CancelledError, Event
from pathlib import Path
from typing import Any

from mentat.session import Session
from mentat.session_stream import StreamMessage, StreamMessageSource


async def ainput(*args: Any, **kwargs: Any):
    return await asyncio.to_thread(input, *args, **kwargs)


class MentatServer:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        self.stopped = Event()
        self.session = Session(self.cwd)

    async def _client_listener(self):
        while not self.stopped.is_set():
            line = await ainput()
            try:
                message = StreamMessage.model_validate_json(line)  # pyright: ignore
            except ValueError:
                logging.error("Invalid StreamMessage recieved")
                break
            self.session.stream.send_stream_message(message)

    async def _stream_listener(self):
        async for message in self.session.stream.universal_listen():
            if message.source == StreamMessageSource.SERVER:
                message_json = StreamMessage.model_dump_json(message)
                print(message_json, flush=True)
            elif message.channel == "session_exit":
                self.stopped.set()
                break

    async def run(self):
        self.session.start()
        logging.debug("Completed startup")

        stream_listener_task = asyncio.create_task(self._stream_listener())
        client_listener_task = asyncio.create_task(self._client_listener())
        await self.stopped.wait()

        try:
            stream_listener_task.cancel()
            client_listener_task.cancel()
        except CancelledError:
            pass


async def run(args: argparse.Namespace):
    try:
        cwd = Path(args.cwd).expanduser().resolve()
        mentat_server = MentatServer(cwd)
        await mentat_server.run()
    except Exception as e:
        logging.error(f"Exception: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Run conversation with command line args",
    )
    parser.add_argument("cwd", help="The working directory for the server to run in")
    args = parser.parse_args()
    asyncio.run(run(args))
