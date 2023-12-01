import asyncio
import logging
import shlex
from typing import Any, Coroutine

from mentat.commands import Command
from mentat.errors import RemoteKeyboardInterrupt, SessionExit
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import StreamMessage


async def _get_input_request(**kwargs: Any) -> StreamMessage:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    message = stream.send("", channel="input_request", **kwargs)
    response = await stream.recv(f"input_request:{message.id}")
    return response


async def collect_user_input(plain: bool = False) -> StreamMessage:
    """
    Listens for user input on a new channel

    send a message requesting user to send a response
    create a new broadcast channel that listens for the input
    close the channel after receiving the input
    """
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    response = await _get_input_request(plain=plain)
    logging.debug(f"User Input: {response.data}")

    # Intercept and run commands
    if not plain:
        while isinstance(response.data, str) and response.data.startswith("/"):
            try:
                arguments = shlex.split(response.data[1:])
                command = Command.create_command(arguments[0])
                await command.apply(*arguments[1:])
            except ValueError as e:
                stream.send(
                    f"Error processing command arguments: {e}", color="light_red"
                )

            response = await _get_input_request(plain=plain)

    # Quit on q
    if isinstance(response.data, str) and response.data.strip() == "q":
        raise SessionExit

    return response


async def ask_yes_no(default_yes: bool) -> bool:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    while True:
        # TODO: combine this into a single message (include content)
        stream.send("(Y/n)" if default_yes else "(y/N)")
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
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

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
            stream.send("\n")

            if raise_exception_on_interrupt:
                raise RemoteKeyboardInterrupt
