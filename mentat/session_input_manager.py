from mentat.session_conversation import SessionConversation


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
        user_input = await self.session_conversation.recv_message()

        return user_input

    async def ask_yes_no(self, default_yes: bool) -> bool:
        while True:
            await self.session_conversation.add_message(
                "(Y/n)" if default_yes else "(y/N)"
            )
            user_input = await self.session_conversation.recv_message()
            if user_input in ["y", "n", ""]:
                break
        return user_input == "y" or (user_input != "n" and default_yes)
