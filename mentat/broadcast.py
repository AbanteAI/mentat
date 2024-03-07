# Adapted from https://github.com/encode/broadcaster
from __future__ import annotations

import asyncio
from asyncio import CancelledError, Queue
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, AsyncGenerator, Dict, Iterator, Set

import attr


# TODO: This entire file is way overengineered and overcomplicated, and vastly needs to be simplified and improved
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
        self._universally_subscribed: bool = False
        self._missed_events: defaultdict[str, list[Event]] = defaultdict(list)

    def connect(self) -> None:
        self._published: Queue[Event] = Queue()

    def disconnect(self) -> None:
        pass

    async def join(self) -> None:
        await self._published.join()

    def subscribe(self, channel: str) -> None:
        self._subscribed.add(channel)
        for event in self._missed_events[channel]:
            self.publish(event.channel, event.message)
        self._missed_events[channel].clear()

    def unsubscribe(self, channel: str) -> None:
        self._subscribed.remove(channel)

    def universal_subscribe(self) -> None:
        self._universally_subscribed = True
        for events in self._missed_events.values():
            for event in events:
                self.publish(event.channel, event.message)
        self._missed_events.clear()

    def universal_unsubscribe(self) -> None:
        self._universally_subscribed = False

    # Since there is no maximum queue size, use the synchronous version of this function instead
    async def publish_async(self, channel: str, message: Any) -> None:
        event = Event(channel=channel, message=message)
        if channel in self._subscribed or self._universally_subscribed:
            await self._published.put(event)
        else:
            self._missed_events[channel].append(event)

    def publish(self, channel: str, message: Any) -> None:
        event = Event(channel=channel, message=message)
        if channel in self._subscribed or self._universally_subscribed:
            self._published.put_nowait(event)
        else:
            self._missed_events[channel].append(event)

    async def next_published(self) -> Event:
        event = await self._published.get()
        self._published.task_done()
        return event


class Unsubscribed(Exception):
    pass


class Broadcast:
    def __init__(self):
        self._subscribers: Dict[str, set[Queue[Event | None]]] = {}
        self._universal_subscribers: set[Queue[Event | None]] = set()
        self._backend = MemoryBackend()

    def __enter__(self) -> Broadcast:
        self.connect()
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        self.disconnect()

    def connect(self) -> None:
        self._backend.connect()
        self._listener_task = asyncio.create_task(self._listener())

    def disconnect(self) -> None:
        if self._listener_task.done():
            try:
                self._listener_task.result()
            except CancelledError:
                pass
        else:
            self._listener_task.cancel()
        self._backend.disconnect()

    async def join(self) -> None:
        """Blocks until all events have been processed"""
        await self._backend.join()

    async def _listener(self) -> None:
        while True:
            event = await self._backend.next_published()
            for queue in self._subscribers.get(event.channel, set()):
                queue.put_nowait(event)
            for queue in self._universal_subscribers:
                queue.put_nowait(event)

    # Since there is no maximum queue size, use the synchronous version of this function instead
    async def publish_async(self, channel: str, message: Any) -> None:
        await self._backend.publish_async(channel, message)

    def publish(self, channel: str, message: Any) -> None:
        self._backend.publish(channel, message)

    @contextmanager
    def subscribe(self, channel: str) -> Iterator[Subscriber]:
        queue: Queue[Event | None] = Queue()

        if not self._subscribers.get(channel):
            self._backend.subscribe(channel)
            self._subscribers[channel] = set()

        self._subscribers[channel].add(queue)
        yield Subscriber(queue)
        self._subscribers[channel].remove(queue)

        if not self._subscribers.get(channel):
            del self._subscribers[channel]
            self._backend.unsubscribe(channel)

    @contextmanager
    def universal_subscribe(self) -> Iterator[Subscriber]:
        queue: Queue[Event | None] = Queue()

        if not self._universal_subscribers:
            self._backend.universal_subscribe()

        self._universal_subscribers.add(queue)
        yield Subscriber(queue)
        self._universal_subscribers.remove(queue)

        if not self._universal_subscribers:
            self._backend.universal_unsubscribe()
