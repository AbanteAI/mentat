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
    """
    Used to send and receive messages from the client.

    Channels and their expected behavior (starred channels are sent by the client):

    default: Any data sent to the client over this channel should be displayed. Valid kwargs: color, style

    *session_exit: Sent by the client, suggesting that the session should exit whenever possible.
    client_exit: Sent by the server directly before shutting down. Client should shut down when received.

    loading: Used to tell the client to display a loading bar. Valid kwargs: progress, terminate

    input_request: Used to request input from the client (data unused). Valid kwargs: plain, command_autocomplete
    *input_request:<message_id>: Sent by the client. The channel the response to an input_request is sent over.

    edits_complete: A boolean sent when edits have been completed. True if any edits were accepted.

    *completion_request: Sent by the client, retrieves completions for given data. Valid kwargs: command_autocomplete
    completion_request:<message_id>: The response to the given completion request.

    default_prompt: The prefilled prompt to show on next user input request. Should be additive and reset
    after every input request. See TerminalClient for exact implementation.

    *interrupt: Sent by the client. Sent whenever client interrupts current work. Equivalent to ctrl-C
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
