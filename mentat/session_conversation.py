from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal
from uuid import UUID, uuid4

from ipdb import set_trace

from .broadcast import Broadcast, Event

_SESSION_CONVERSATION: ContextVar[SessionConversation] = ContextVar(
    "mentat:session_conversation"
)


def get_session_conversation():
    return _SESSION_CONVERSATION.get()


class MessageData:
    def __init__(self, content: Any, **kwargs):
        self.content = content
        self.extra = kwargs


# must be json serializable
@dataclass
class Message:
    id: UUID
    source: Literal["server"] | Literal["client"]
    data: Any
    created_at: datetime


class MessageGroup:
    def __init__(self):
        self.data: List[Dict] = []

    def add(self, content: str, **kwargs):
        self.data.append({"content": content, **kwargs})


class SessionConversation:
    """Replaces `cprint` and `print`

    Stores message history for a Session and holds an in-memory message bus.

    Terminal and extension clients can read these messages and render them accordingly.
    For the terminal, they would be rendered with `cprint`.
    """

    def __init__(self):
        self.messages: List[Message] = []
        self.broadcast = Broadcast()

    async def start(self):
        await self.broadcast.connect()

    async def stop(self):
        await self.broadcast.disconnect()

    # TODO: make this the default send method (non-async)
    def send_message_nowait(
        self,
        data: Any,
        source: Literal["server"] | Literal["client"] = "server",
        channel: str = "default",
    ):
        if isinstance(data, str):
            data = {"content": data}

        message = Message(
            id=uuid4(), source=source, data=data, created_at=datetime.utcnow()
        )
        self.messages.append(message)
        self.broadcast.publish_nowait(channel=channel, message=message)

        return message

    async def send_message(
        self,
        data: Any,
        source: Literal["server"] | Literal["client"] = "server",
        channel: str = "default",
    ):
        # TODO: make this cleaner
        if isinstance(data, str):
            data = {"content": data}

        message = Message(
            id=uuid4(), source=source, data=data, created_at=datetime.utcnow()
        )
        self.messages.append(message)
        await self.broadcast.publish(channel=channel, message=message)

        return message

    # TODO: this should aways return a Message
    async def recv_message(self, channel: str = "default"):
        """Listen for a single reponse on a channel"""
        async with self.broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                message: Message = event.message
                return message

    # TODO: this should aways return Messages
    async def listen(self, channel: str = "default"):
        """Listen to all messages on a channel indefinitely"""
        async with self.broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                message: Message = event.message
                yield message
