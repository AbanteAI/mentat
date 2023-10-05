import pytest

from mentat.broadcast import Broadcast


@pytest.mark.asyncio
async def test_broadcast():
    async with Broadcast() as broadcast:
        async with broadcast.subscribe("chatroom") as subscriber:
            await broadcast.publish("chatroom", "hello")
            event = await subscriber.get()
            assert event.channel == "chatroom"
            assert event.message == "hello"
