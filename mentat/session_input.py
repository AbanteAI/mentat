import asyncio
import logging
from typing import Any, Coroutine

from .errors import RemoteKeyboardInterrupt
from .session_stream import SESSION_STREAM, StreamMessage


async def collect_user_input(**kwargs: Any) -> StreamMessage:
    """Listens for user input on a new channel

    send a message requesting user to send a response
    create a new broadcast channel that listens for the input
    close the channel after receiving the input
    """
    stream = SESSION_STREAM.get()

    message = await stream.send("", channel="input_request", **kwargs)
    response = await stream.recv(f"input_request:{message.id}")

    logging.debug(f"User Input: {response.data}")

    return response


async def ask_yes_no(default_yes: bool) -> bool:
    stream = SESSION_STREAM.get()

    while True:
        # TODO: combine this into a single message (include content)
        await stream.send("(Y/n)" if default_yes else "(y/N)")
        response = await collect_user_input(plain=True)
        content = response.data
        if content in ["y", "n", ""]:
            break
    return content == "y" or (content != "n" and default_yes)


async def listen_for_interrupt(
    coro: Coroutine[None, None, Any], raise_exception_on_interrupt: bool = True
):
    """Listens for an 'interrupt' message from a client

    This function is used to cancel long-running coroutines from a remote client. If a
    message is received on the "interrupt" channel for the current session stream, the
    asyncio.Task created from `coro` will be canceled.

    TODO:
    - make sure task cancellation actually cancels the tasks
      - Is there any kind of delay, or a possiblity of one?
    - make sure there's no race conditions

    The `.result()` call for `wrapped_task` will re-raise any exceptions thrown
    inside of that Task.
    """
    stream = SESSION_STREAM.get()

    async with stream.interrupt_lock:
        interrupt_task = asyncio.create_task(stream.recv("interrupt"))
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

        if wrapped_task in done:
            return wrapped_task.result()
        else:
            # Send a newline for terminal clients (remove later)
            await stream.send("\n")

            if raise_exception_on_interrupt:
                raise RemoteKeyboardInterrupt
