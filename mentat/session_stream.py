from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, cast
from uuid import UUID, uuid4

from mentat.broadcast import Broadcast


class StreamMessageSource(Enum):
    SERVER = "server"
    CLIENT = "client"


@dataclass(slots=True)
class StreamMessage:
    id: UUID
    channel: str
    source: StreamMessageSource
    data: Any
    extra: Dict[str, Any]
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

    def start(self):
        self._broadcast.connect()

    def stop(self):
        self._broadcast.disconnect()

    # Since there is no maximum queue size, use the synchronous version of this function instead
    async def send_async(
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
        await self._broadcast.publish_async(channel=channel, message=message)

        return message

    def send(
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
        self._broadcast.publish(channel=channel, message=message)

        return message

    async def recv(self, channel: str = "default") -> StreamMessage:
        """Listen for a single event on a channel"""
        with self._broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                stream_message = cast(StreamMessage, event.message)
                return stream_message
            raise Exception("recv should not complete without receiving an Event")

    async def listen(
        self, channel: str = "default"
    ) -> AsyncGenerator[StreamMessage, None]:
        """Listen to all messages on a channel indefinitely"""
        with self._broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                yield event.message

    async def join(self) -> None:
        """Blocks until all sent events have been processed"""
        await self._broadcast.join()
