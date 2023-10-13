# Adapted from https://github.com/encode/broadcaster

import asyncio
from asyncio import Queue
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, AsyncIterator, Dict, Set

import attr


@attr.define
class Event:
    channel: str = attr.field()
    message: Any = attr.field()


class Subscriber:
    def __init__(self, queue: Queue[Event | None]) -> None:
        self._queue = queue

    async def __aiter__(self) -> AsyncGenerator[Event, None]:
        try:
            while True:
                yield await self.get()
        except Unsubscribed:
            pass

    async def get(self) -> Event:
        item = await self._queue.get()
        if item is None:
            raise Unsubscribed()
        return item


class MemoryBackend:
    def __init__(self):
        self._subscribed: Set[str] = set()
        self._missed_events: defaultdict[str, list[Event]] = defaultdict(list)

    async def connect(self) -> None:
        self._published: Queue[Event] = Queue()

    async def disconnect(self) -> None:
        pass

    async def subscribe(self, channel: str) -> None:
        self._subscribed.add(channel)
        for event in self._missed_events[channel]:
            await self.publish(event.channel, event.message)
        self._missed_events[channel].clear()

    async def unsubscribe(self, channel: str) -> None:
        self._subscribed.remove(channel)

    async def publish(self, channel: str, message: Any) -> None:
        event = Event(channel=channel, message=message)
        if channel in self._subscribed:
            await self._published.put(event)
        else:
            self._missed_events[channel].append(event)

    async def next_published(self) -> Event:
        while True:
            return await self._published.get()


class Unsubscribed(Exception):
    pass


class Broadcast:
    def __init__(self):
        self._subscribers: Dict[str, set[Queue[Event | None]]] = {}
        self._backend = MemoryBackend()

    async def __aenter__(self) -> "Broadcast":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        await self._backend.connect()
        self._listener_task = asyncio.create_task(self._listener())

    async def disconnect(self) -> None:
        if self._listener_task.done():
            self._listener_task.result()
        else:
            self._listener_task.cancel()
        await self._backend.disconnect()

    async def _listener(self) -> None:
        while True:
            event = await self._backend.next_published()
            for queue in list(self._subscribers.get(event.channel, set())):
                await queue.put(event)

    async def publish(self, channel: str, message: Any) -> None:
        await self._backend.publish(channel, message)

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[Subscriber]:
        queue: Queue[Event | None] = Queue()

        try:
            if not self._subscribers.get(channel):
                await self._backend.subscribe(channel)
                self._subscribers[channel] = set()

            self._subscribers[channel].add(queue)
            yield Subscriber(queue)
            self._subscribers[channel].remove(queue)

            if not self._subscribers.get(channel):
                del self._subscribers[channel]
                await self._backend.unsubscribe(channel)
        finally:
            await queue.put(None)
