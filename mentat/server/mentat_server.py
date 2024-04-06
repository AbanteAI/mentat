import argparse
import asyncio
import logging
from asyncio import CancelledError, Event
from io import TextIOWrapper
from pathlib import Path

from mentat.config import Config
from mentat.session import Session
from mentat.session_stream import StreamMessage, StreamMessageSource


async def ainput(fd_input: TextIOWrapper):
    return await asyncio.to_thread(fd_input.readline)


class MentatServer:
    def __init__(self, cwd: Path, config: Config) -> None:
        self.cwd = cwd
        self.stopped = Event()
        self.session = Session(self.cwd, config=config, apply_edits=False, show_update=False)

    async def _client_listener(self):
        with open(3) as fd_input:
            try:
                while not self.stopped.is_set():
                    line = await ainput(fd_input)
                    try:
                        message = StreamMessage.model_validate_json(line)  # pyright: ignore
                        self.session.stream.send_stream_message(message)
                    except ValueError:
                        logging.error(f"Invalid StreamMessage recieved: {line}")
            except Exception as e:
                logging.error(f"Error: {e}")

    async def _stream_listener(self):
        with open(4, "w") as fd_output:
            async for message in self.session.stream.universal_listen():
                if message.source == StreamMessageSource.SERVER:
                    message_json = StreamMessage.model_dump_json(message)
                    fd_output.write(message_json + "\n")
                    fd_output.flush()
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
        config = Config.create(cwd, args)
        mentat_server = MentatServer(cwd, config)
        await mentat_server.run()
    except Exception as e:
        logging.error(f"Exception: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Run conversation with command line args",
    )
    parser.add_argument("cwd", help="The working directory for the server to run in")
    Config.add_fields_to_argparse(parser)

    args = parser.parse_args()
    asyncio.run(run(args))
