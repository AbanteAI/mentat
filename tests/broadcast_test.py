import pytest

from mentat.broadcast import Broadcast


@pytest.mark.asyncio
async def test_broadcast():
    with Broadcast() as broadcast:
        with broadcast.subscribe("chatroom") as subscriber:
            broadcast.publish("chatroom", "hello")
            event = await subscriber.get()
            assert event.channel == "chatroom"
            assert event.message == "hello"
