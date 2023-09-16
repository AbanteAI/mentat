from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import UUID, uuid4

from .broadcast import Broadcast


@dataclass
class Message:
    id: UUID
    content: str
    extra: Dict[str, Any] | None = None


@dataclass
class InputRequest:
    id: UUID


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

    async def add_message(self, content: str, **kwargs):
        message = Message(id=uuid4(), content=content, extra=kwargs)
        self.messages.append(message)
        await self.broadcast.publish("default", message)

    async def recv_message(self):
        input_request = InputRequest(id=uuid4())
        await self.broadcast.publish("default", input_request)
        async with self.broadcast.subscribe(
            f"default:{input_request.id}"
        ) as subscriber:
            async for event in subscriber:
                return event

    async def listen(self):
        async with self.broadcast.subscribe("default") as subscriber:
            async for event in subscriber:
                yield event
