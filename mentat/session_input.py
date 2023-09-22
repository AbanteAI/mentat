import asyncio
import logging
from typing import Coroutine

from ipdb import set_trace

from .errors import RemoteKeyboardInterrupt
from .session_stream import SessionMessage, get_session_stream

logger = logging.getLogger()


async def collect_user_input() -> SessionMessage:
    """Listens for user input on a new channel

    send a message requesting user to send a response
    create a new broadcast channel that listens for the input
    close the channel after receiving the input
    """
    stream = get_session_stream()

    data = {"type": "collect_user_input"}
    message = stream.send(data)
    response = await stream.recv(f"default:{message.id}")

    return response


async def ask_yes_no(default_yes: bool) -> bool:
    stream = get_session_stream()

    while True:
        # TODO: combine this into a single message (include content)
        stream.send("(Y/n)" if default_yes else "(y/N)")
        response = await collect_user_input()
        content = response.data["content"]
        if content in ["y", "n", ""]:
            break
    return content == "y" or (content != "n" and default_yes)


async def listen_for_interrupt(
    coro: Coroutine, raise_exception_on_interrupt: bool = True
):
    """
    TODO:
    - handle exceptions raised by either task
    - make sure task cancellation actually cancels the tasks
      - Is there any kind of delay, or a possiblity of one?
    - make sure there's no race conditions

    The `.result()` call for `wrapped_task` will re-raise any exceptions thrown
    inside of that Task.
    """
    stream = get_session_stream()

    async def _listen_for_interrupt():
        async for message in stream.listen():
            if message.source == "client":
                if message.data.get("message_type") == "interrupt":
                    return

    interrupt_task = asyncio.create_task(_listen_for_interrupt())
    wrapped_task = asyncio.create_task(coro)

    done, pending = await asyncio.wait(
        {interrupt_task, wrapped_task}, return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            set_trace()
            raise e

    if wrapped_task in done:
        return wrapped_task.result()
    else:
        raise RemoteKeyboardInterrupt
