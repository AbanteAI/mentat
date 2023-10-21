import asyncio
from asyncio import Event
from asyncio.tasks import Task
from pathlib import Path
from typing import List

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
        use_embeddings: bool = True,
        auto_tokens: int = 0,
    ):
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.diff = diff
        self.pr_diff = pr_diff
        self.no_code_map = no_code_map
        self.use_embeddings = use_embeddings
        self.auto_tokens = auto_tokens

        self._accumulated_message = ""
        self.exited = Event()

    async def call_mentat(self, message: str):
        input_request_message = await self.session.stream.recv("input_request")
        self.session.stream.send(
            message,
            source=StreamMessageSource.CLIENT,
            channel=f"input_request:{input_request_message.id}",
        )

        temp = self._accumulated_message
        self._accumulated_message = ""
        return temp

    async def call_mentat_auto_accept(self, message: str):
        await self.call_mentat(message)
        if self.exited.is_set():
            return
        await self.call_mentat("y")

    async def wait_for_edit_completion(self):
        await self.session.stream.recv(channel="edits_complete")

    async def _accumulate_messages(self):
        async for message in self.session.stream.listen():
            end = "\n"
            if message.extra and isinstance(message.extra.get("end"), str):
                end = message.extra["end"]
            self._accumulated_message += message.data + end

    async def _listen_for_exit(self):
        await self.session.stream.recv("exit")
        await self.stop()

    async def startup(self):
        self.session = Session(
            self.paths,
            self.exclude_paths,
            self.diff,
            self.pr_diff,
            self.no_code_map,
            self.use_embeddings,
            self.auto_tokens,
        )
        self.session.start()
        self.acc_task = asyncio.create_task(self._accumulate_messages())
        self.exit_task: Task[None] = asyncio.create_task(self._listen_for_exit())

    async def stop(self):
        await self.session.stop()
        self.acc_task.cancel()
        self.exit_task.cancel()
        self.exited.set()
