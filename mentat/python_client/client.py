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
        diff: str | None = None,
        pr_diff: str | None = None,
        no_code_map: bool = False,
        use_embedding: bool = True,
        auto_tokens: int = 0,
    ):
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.diff = diff
        self.pr_diff = pr_diff
        self.no_code_map = no_code_map
        self.use_embedding = use_embedding
        self.auto_tokens = auto_tokens

        self.session: Session | None = None

        self._tasks: Set[asyncio.Task[None]] = set()
        self.acc_task: asyncio.Task[None] | None = None
        self.started = False
        self._accumulated_message = ""

    async def call_mentat(self, message: str):
        assert isinstance(self.session, Session), "Client is not running"

        input_request_message = await self.session.stream.recv("input_request")
        await self.session.stream.send(
            message,
            source=StreamMessageSource.CLIENT,
            channel=f"input_request:{input_request_message.id}",
        )

        temp = self._accumulated_message
        self._accumulated_message = ""
        return temp

    async def call_mentat_auto_accept(self, message: str):
        await self.call_mentat(message)
        if not self.started:
            return
        await self.call_mentat("y")

    async def wait_for_edit_completion(self):
        assert isinstance(self.session, Session), "Client is not running"
        await self.session.stream.recv(channel="edits_complete")

    async def _accumulate_messages(self):
        assert isinstance(self.session, Session), "Client is not running"
        async for message in self.session.stream.listen():
            end = "\n"
            if message.extra and isinstance(message.extra.get("end"), str):
                end = message.extra["end"]
            self._accumulated_message += message.data + end

    async def startup(self):
        self.session = await Session.create(
            self.paths,
            self.exclude_paths,
            self.diff,
            self.pr_diff,
            self.no_code_map,
            self.use_embedding,
            self.auto_tokens,
        )
        asyncio.ensure_future(self.session.start())
        self.acc_task = asyncio.create_task(self._accumulate_messages())
        self.started = True

    async def stop(self):
        if self.session is not None:
            stop_task = self.session.stop()
            if stop_task is not None:
                await stop_task
            self.session = None
        if self.acc_task is not None:
            self.acc_task.cancel()
            self.acc_task = None
        self.started = False
