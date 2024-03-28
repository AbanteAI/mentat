from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel

from mentat.broadcast import Broadcast


class StreamMessageSource:
    # Enums can't be serialized or deserialized, since Enum.value is an instance of Enum, not the actual value
    TYPE = Literal["server", "client"]
    SERVER = "server"
    CLIENT = "client"


class StreamMessage(BaseModel):
    id: UUID
    channel: str
    source: StreamMessageSource.TYPE
    data: Any
    extra: Dict[str, Any]


class SessionStream:
    """
    Used to send and receive messages from the client.

    Channels and their expected behavior (starred channels are sent by the client):

    default: Any data sent to the client over this channel should be displayed.
    Valid kwargs: color, style, filepath, filepath_display, delimiter

    *session_exit: Sent by the client, suggesting that the session should exit whenever possible.
    client_exit: Sent by the server, client should shut down when received.
    session_stopped: Sent by the server directly before server shuts down. Server can't be contacted after received.

    loading: Used to tell the client to display a loading bar. Valid kwargs: terminate

    input_request: Used to request input from the client (data unused). Valid kwargs: command_autocomplete
    *input_request:<message_id>: Sent by the client. The channel the response to an input_request is sent over.

    model_file_edits: Once the model fully completes its response, sends a list of the file edits. Schema:
    [
        {
            "file_path": "/absolute/path/to/file",
            "new_file_path": "/absolute/path/to/renamed_file", # May be null
            "type": "edit" | "creation" | "deletion",
            "new_content": "The new file text after edits are applied"
        },
        ...
    ]

    edits_complete: A boolean sent when edits have been completed. True if any edits were accepted.

    *completion_request: Sent by the client, retrieves completions for given data. Valid kwargs: command_autocomplete
    completion_request:<message_id>: The response to the given completion request.

    default_prompt: The prefilled prompt to show on next user input request. Should be additive and reset
    after every input request. See TerminalClient for exact implementation.

    interruptable: A boolean sent to enable or disable an 'interrupt' button.
    If an interrupt is sent while interruptable is false, the server will shut down.
    *interrupt: Sent by the client. Sent whenever client interrupts current work. Sent by things like Ctrl-C.

    context_update: An object describing the context sent whenever the context changes. Schema:
    {
        "cwd": "Mentat's cwd",
        "diff_context_display": "The display for the diff context",
        "auto_context_tokens": The number of auto context tokens,
        "features": ["List of user included features"],
        "git_diff_paths": ["List of all paths with git diffs; used to color the changed included features"],
        "total_tokens": Total tokens in context,
        "maximum_tokens": Maximum tokens allowed in context,
        "total_cost": Total cost so far
    }

    *include: Sent by the client. Gives a path to include in context.
    *exclude: Sent by the client. Gives a path to exclude from context.
    *clear_conversation: Sent by the client. Clears the conversation history (but not the context).
    """

    def __init__(self):
        self.messages: List[StreamMessage] = []
        self._interrupt_lock = asyncio.Lock()
        self._broadcast = Broadcast()

    def start(self):
        self._broadcast.connect()

    def stop(self):
        self._broadcast.disconnect()

    # Since there is no maximum queue size, use the synchronous version of this function instead
    async def send_async(
        self,
        data: Any,
        source: StreamMessageSource.TYPE = StreamMessageSource.SERVER,
        channel: str = "default",
        **kwargs: Any,
    ):
        message = StreamMessage(
            id=uuid4(),
            source=source,
            channel=channel,
            data=data,
            extra=kwargs,
        )

        self.messages.append(message)
        await self._broadcast.publish_async(channel=channel, message=message)

        return message

    def send(
        self,
        data: Any,
        source: StreamMessageSource.TYPE = StreamMessageSource.SERVER,
        channel: str = "default",
        **kwargs: Any,
    ):
        message = StreamMessage(
            id=uuid4(),
            source=source,
            channel=channel,
            data=data,
            extra=kwargs,
        )

        self.messages.append(message)
        self._broadcast.publish(channel=channel, message=message)

        return message

    def send_stream_message(self, message: StreamMessage):
        self.messages.append(message)
        self._broadcast.publish(channel=message.channel, message=message)

    async def recv(self, channel: str = "default") -> StreamMessage:
        """Listen for a single event on a channel"""
        with self._broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                stream_message = cast(StreamMessage, event.message)
                return stream_message
            raise Exception("recv should not complete without receiving an Event")

    async def listen(self, channel: str = "default") -> AsyncGenerator[StreamMessage, None]:
        """Listen to all messages on a channel indefinitely"""
        with self._broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                yield event.message

    async def universal_listen(self) -> AsyncGenerator[StreamMessage, None]:
        with self._broadcast.universal_subscribe() as subscriber:
            async for event in subscriber:
                yield event.message

    async def join(self) -> None:
        """Blocks until all sent events have been processed"""
        await self._broadcast.join()

    @asynccontextmanager
    async def interrupt_catcher(self, event: asyncio.Event):
        """
        Will start a task listening for an interrupt, set the given event when one is received, and clear it at the end
        """

        interrupt_task = asyncio.create_task(self._listen_for_interrupt(event))
        self.send(True, channel="interruptable")
        yield
        self.send(False, channel="interruptable")
        interrupt_task.cancel()
        try:
            await interrupt_task
        except asyncio.CancelledError:
            pass
        event.clear()

    async def _listen_for_interrupt(self, event: asyncio.Event):
        """
        Listens for an interrupt message from the client. Set the event given when an intterupt is received.
        """

        async with self._interrupt_lock:
            await self.recv("interrupt")
            logging.info("User sent interrupt.")
            event.set()

    def is_interrupt_locked(self) -> bool:
        return self._interrupt_lock.locked()
