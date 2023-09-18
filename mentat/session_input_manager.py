import asyncio
import logging
from typing import Coroutine

from ipdb import set_trace

from .errors import RemoteKeyboardInterrupt
from .session_conversation import Message, SessionConversation

logger = logging.getLogger()


class SessionInputManager:
    """Replaces `UserInputManager`

    An instance of this is passed around to various functions similar to how
    `UserInputManager` is used.
    """

    def __init__(self, session_conversation: SessionConversation):
        self.session_conversation = session_conversation

    async def collect_user_input(self):
        # send a message requesting user to send a response
        # create a new broadcast channel that listens for the input
        # close the channel after receiving the input
        data = {"type": "collect_user_input"}
        message = await self.session_conversation.send_message(
            source="server", data=data
        )
        response = await self.session_conversation.recv_message(f"default:{message.id}")

        return response

    async def ask_yes_no(self, default_yes: bool) -> bool:
        while True:
            # TODO: combine this into a single message (include content)
            await self.session_conversation.send_message(
                source="server", data=dict(content="(Y/n)" if default_yes else "(y/N)")
            )
            response = await self.collect_user_input()
            assert isinstance(response, Message)
            content = response.data["content"]
            if content in ["y", "n", ""]:
                break
        return content == "y" or (content != "n" and default_yes)

    async def listen_for_interrupt(
        self, coro: Coroutine, raise_exception_on_interrupt: bool = True
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

        async def _listen_for_interrupt():
            async for message in self.session_conversation.listen():
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

        if wrapped_task in done:
            return wrapped_task.result()
        else:
            raise RemoteKeyboardInterrupt
