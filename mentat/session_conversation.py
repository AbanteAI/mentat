from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal
from uuid import UUID, uuid4

from ipdb import set_trace

from .broadcast import Broadcast


# must be json serializable
@dataclass
class Message:
    source: Literal["server"] | Literal["client"]
    data: Any
    id: UUID = uuid4()
    created_at: datetime = datetime.utcnow()


class MessageGroup:
    def __init__(self):
        self.data: List[Dict] = []

    def add(self, content: str, **kwargs):
        self.data.append({"content": content, **kwargs})


class SessionConversation:
    """Replaces `cprint` and `print`

    Stores message history for a Session and holds an in-memory message bus.

    Terminal and extension clients  can read these messages and render them accordingly.
    For the terminal, they would be rendered with `cprint`.
    """

    def __init__(self):
        self.messages: List[Message] = []
        self.broadcast = Broadcast()

    async def start(self):
        await self.broadcast.connect()

    async def stop(self):
        await self.broadcast.disconnect()

    async def send_message(
        self,
        source: Literal["server"] | Literal["client"],
        data: Any,
        channel: str = "default",
    ):
        message = Message(
            id=uuid4(), source=source, data=data, created_at=datetime.utcnow()
        )
        self.messages.append(message)
        await self.broadcast.publish(channel=channel, message=message)

    async def recv_message(self, channel: str = "default"):
        """Listen for a single reponse on a temporary channel"""
        input_request_message = Message(source="server", data={"type": "input_request"})
        await self.broadcast.publish("default", input_request_message)
        async with self.broadcast.subscribe(
            f"default:{input_request_message.id}"
        ) as subscriber:
            async for event in subscriber:
                return event

    async def listen(self, channel: str = "default"):
        """Listen to all messages on a channel indefinitely"""
        async with self.broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                yield event
