import asyncio
import logging
import shlex
from typing import Any, Coroutine

from mentat.command.command import Command
from mentat.errors import RemoteKeyboardInterrupt, SessionExit
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import StreamMessage


async def _get_input_request(**kwargs: Any) -> StreamMessage:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    message = stream.send("", channel="input_request", **kwargs)
    response = await stream.recv(f"input_request:{message.id}")
    logging.debug(f"User Input: {response.data}")
    return response


async def collect_user_input(
    plain: bool = False, command_autocomplete: bool = False
) -> StreamMessage:
    """
    Listens for user input on a new channel

    send a message requesting user to send a response
    create a new broadcast channel that listens for the input
    close the channel after receiving the input
    """

    response = await _get_input_request(
        plain=plain, command_autocomplete=command_autocomplete
    )
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
        content = response.data.strip().lower()
        if content in ["y", "n", ""]:
            break
    return content == "y" or (content != "n" and default_yes)


async def collect_input_with_commands() -> StreamMessage:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    response = await collect_user_input(command_autocomplete=True)
    while isinstance(response.data, str) and response.data.startswith("/"):
        try:
            # We only use shlex to split the arguments, not the command itself
            arguments = shlex.split(" ".join(response.data.split(" ")[1:]))
            command = Command.create_command(response.data[1:].split(" ")[0])
            await command.apply(*arguments)
        except ValueError as e:
            stream.send(f"Error processing command arguments: {e}", style="error")
        response = await collect_user_input(command_autocomplete=True)
    return response


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
