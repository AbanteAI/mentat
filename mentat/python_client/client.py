import asyncio
from pathlib import Path
from typing import List, Set

from mentat.session import Session
from mentat.session_stream import StreamMessageSource


class PythonClient:
    def __init__(
        self,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        no_code_map: bool = False,
        diff: str | None = None,
        pr_diff: str | None = None,
    ):
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.no_code_map = no_code_map
        self.diff = diff
        self.pr_diff = pr_diff

        self.session: Session | None = None

        self._tasks: Set[asyncio.Task[None]] = set()
        self.acc_task: asyncio.Task[None] | None = None
        self._started = False
        self._accumulated_message = ""
        self._input_request_message = None

    async def call_mentat(self, message: str):
        if not self._started:
            await self._startup()
        await self.session.stream.send(
            message,
            source=StreamMessageSource.CLIENT,
            channel=f"input_request:{self._input_request_message.id}",
        )
        self._input_request_message = await self.session.stream.recv("input_request")
        temp = self._accumulated_message
        self._accumulated_message = ""
        return temp

    async def call_mentat_auto_accept(self, message: str):
        await self.call_mentat(message)
        await self.call_mentat("y")

    async def _accumulate_messages(self):
        assert isinstance(self.session, Session), "Client is not running"
        async for message in self.session.stream.listen():
            self._accumulated_message += message.data

    async def _startup(self):
        self.session = await Session.create(
            self.paths, self.exclude_paths, self.no_code_map, self.diff, self.pr_diff
        )
        asyncio.ensure_future(self.session.start())
        self._input_request_message = await self.session.stream.recv("input_request")

        self.acc_task = asyncio.create_task(self._accumulate_messages())
        self._started = True

    async def stop(self):
        if self.session is not None:
            await self.session.stop()
            self.session = None
        if self.acc_task is not None:
            self.acc_task.cancel()
            self.acc_task = None
        self._started = False
