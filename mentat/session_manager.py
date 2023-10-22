import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Set
from uuid import UUID

from .session import Session


class SessionManager:
    def __init__(self):
        self.sessions: Dict[UUID, Session] = {}

        self._tasks: Set[asyncio.Task[None]] = set()

    def _create_task(self, coro: Coroutine[None, None, Any]):
        """Utility method for running a Task in the background"""

        def task_cleanup(task: asyncio.Task[None]):
            self._tasks.remove(task)

        task = asyncio.create_task(coro)
        task.add_done_callback(task_cleanup)
        self._tasks.add(task)

        return task

    async def create_session(
        self,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        on_input_request: Callable | None = None,
        on_output: Callable | None = None,
    ):
        session = await Session.create(paths, exclude_paths)
        session.start()
        self.sessions[session.id] = session
        if on_input_request is not None:
            self._create_task(on_input_request(session))
        if on_output is not None:
            self._create_task(on_output(session))

        return session

    async def shutdown(self):
        # Stop all background tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop all sessions
        session_stop_tasks: List[asyncio.Task[None]] = []
        for session in self.sessions.values():
            session_stop_task = session.stop()
            if session_stop_task is not None:
                session_stop_tasks.append(session_stop_task)
        await asyncio.gather(*session_stop_tasks, return_exceptions=True)
