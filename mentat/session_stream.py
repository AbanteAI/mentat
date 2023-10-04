from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, cast
from uuid import UUID, uuid4

from .broadcast import Broadcast

SESSION_STREAM: ContextVar[SessionStream] = ContextVar("mentat:session_stream")


class StreamMessageSource(Enum):
    SERVER = "server"
    CLIENT = "client"


@dataclass(slots=True)
class StreamMessage:
    id: UUID
    channel: str
    source: StreamMessageSource
    data: Any
    extra: Dict[str, Any] | None
    created_at: datetime


class SessionStream:
    """Replaces `cprint` and `print`

    Stores message history for a Session and holds an in-memory message bus.

    Terminal and extension clients can read these messages and render them accordingly.
    For the terminal, they would be rendered with `cprint`.
    """

    def __init__(self):
        self.messages: List[StreamMessage] = []
        self.interrupt_lock = asyncio.Lock()
        self._broadcast = Broadcast()

    async def start(self):
        await self._broadcast.connect()

    async def stop(self):
        await self._broadcast.disconnect()

    async def send(
        self,
        data: Any,
        source: StreamMessageSource = StreamMessageSource.SERVER,
        channel: str = "default",
        **kwargs: Any,
    ):
        message = StreamMessage(
            id=uuid4(),
            source=source,
            channel=channel,
            data=data,
            created_at=datetime.utcnow(),
            extra=kwargs,
        )

        self.messages.append(message)
        await self._broadcast.publish(channel=channel, message=message)

        return message

    async def recv(self, channel: str = "default") -> StreamMessage:
        """Listen for a single event on a channel"""
        async with self._broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                stream_message = cast(StreamMessage, event.message)
                return stream_message
            raise Exception("recv should not complete without receiving an Event")

    async def listen(
        self, channel: str = "default"
    ) -> AsyncGenerator[StreamMessage, None]:
        """Listen to all messages on a channel indefinitely"""
        async with self._broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                yield event.message
