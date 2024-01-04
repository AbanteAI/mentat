import asyncio

import pytest

from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no


@pytest.mark.asyncio
async def test_ask_yes_no():
    stream = SESSION_CONTEXT.get().stream
    stream.start()

    # Test when user inputs invalid confirmation
    ask_yes_no_task = asyncio.create_task(ask_yes_no(default_yes=False))
    input_request_message = await stream.recv("input_request")
    stream.send("yes", channel=f"input_request:{input_request_message.id}")
    input_request_message = await stream.recv("input_request")
    stream.send("y", channel=f"input_request:{input_request_message.id}")
    assert await ask_yes_no_task is True

    # Test when user inputs 'Y'
    ask_yes_no_task = asyncio.create_task(ask_yes_no(default_yes=False))
    input_request_message = await stream.recv("input_request")
    stream.send("Y", channel=f"input_request:{input_request_message.id}")
    assert await ask_yes_no_task is True

    # Test when user inputs nothing
    ask_yes_no_task = asyncio.create_task(ask_yes_no(default_yes=False))
    input_request_message = await stream.recv("input_request")
    stream.send("", channel=f"input_request:{input_request_message.id}")
    assert await ask_yes_no_task is False

    # Test when user inputs 'n'
    ask_yes_no_task = asyncio.create_task(ask_yes_no(default_yes=False))
    input_request_message = await stream.recv("input_request")
    stream.send("n", channel=f"input_request:{input_request_message.id}")
    assert await ask_yes_no_task is False

    # Test default true
    ask_yes_no_task = asyncio.create_task(ask_yes_no(default_yes=True))
    input_request_message = await stream.recv("input_request")
    stream.send("", channel=f"input_request:{input_request_message.id}")
    assert await ask_yes_no_task is True

    stream.stop()
