import argparse
import asyncio
import logging
from pathlib import Path

from mentat.config import Config
from mentat.session import Session

HOST = "127.0.0.1"
PORT = "7798"


class MentatServer:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        self.stopped = asyncio.Event()
        self.session = Session(self.cwd)

    def _client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.session.stream.listen

    async def run(self):
        self.session.start()
        logging.debug("Completed startup")

        server = await asyncio.start_server(
            self._client_connected, host=HOST, port=PORT
        )
        await self.stopped.wait()
        server.close()


def main():
    parser = argparse.ArgumentParser(
        description="Run conversation with command line args",
    )
    parser.add_argument("cwd", help="The working directory for the server to run in")
    args = parser.parse_args()

    cwd = Path(args.cwd).expanduser().resolve()
    mentat_server = MentatServer(cwd)
    asyncio.run(mentat_server.run())
