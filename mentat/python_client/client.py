import asyncio
from asyncio import Event
from asyncio.tasks import Task
from pathlib import Path
from typing import List

from mentat.config import Config
from mentat.errors import MentatError
from mentat.session import Session
from mentat.session_stream import StreamMessageSource


class PythonClient:
    def __init__(
        self,
        cwd: Path = Path.cwd(),
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        ignore_paths: List[Path] = [],
        diff: str | None = None,
        pr_diff: str | None = None,
        config: Config = Config(),
    ):
        self.cwd = cwd.expanduser().resolve()
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.ignore_paths = ignore_paths
        self.diff = diff
        self.pr_diff = pr_diff
        self.config = config

        self._accumulated_message = ""
        self.stopped = Event()
        self._call_mentat_task = None

    async def _call_mentat(self, message: str):
        input_request_message = await self.session.stream.recv("input_request")
        self.session.stream.send(
            message,
            source=StreamMessageSource.CLIENT,
            channel=f"input_request:{input_request_message.id}",
        )
        if message.strip().lower() == "y":
            await self.wait_for_edit_completion()

        temp = self._accumulated_message
        self._accumulated_message = ""
        return temp

    async def call_mentat(self, message: str):
        self._call_mentat_task = asyncio.create_task(self._call_mentat(message))
        try:
            return await self._call_mentat_task
        except asyncio.CancelledError:
            print(self.session.error)
            raise MentatError("Session failed")

    async def call_mentat_auto_accept(self, message: str):
        await self.call_mentat(message)
        await self.call_mentat("y")

    async def wait_for_edit_completion(self):
        await self.session.stream.recv(channel="edits_complete")

    async def _accumulate_messages(self):
        async for message in self.session.stream.listen():
            end = "\n"
            if isinstance(message.extra.get("end"), str):
                end = message.extra["end"]
            self._accumulated_message += message.data + end

    async def _listen_for_client_exit(self):
        await self.session.stream.recv("client_exit")
        await self._stop()

    async def startup(self):
        self.session = Session(
            self.cwd,
            self.paths,
            self.exclude_paths,
            self.ignore_paths,
            self.diff,
            self.pr_diff,
            self.config,
        )
        self.session.start()
        self.acc_task = asyncio.create_task(self._accumulate_messages())
        self.exit_task: Task[None] = asyncio.create_task(self._listen_for_client_exit())

    async def shutdown(self):
        """Sends the stop signal to the session and returns when client is fully shutdown."""
        self.session.stream.send(None, channel="session_exit")
        await self.stopped.wait()

    async def _stop(self):
        self.acc_task.cancel()
        self.exit_task.cancel()
        if self._call_mentat_task:
            self._call_mentat_task.cancel()
        self.stopped.set()

    def get_conversation(self):
        return self.session.ctx.conversation

    def get_cost_tracker(self):
        return self.session.ctx.cost_tracker
