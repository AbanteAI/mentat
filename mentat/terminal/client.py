import asyncio
import logging

from termcolor import cprint

from mentat.conversation import MentatConversation
from mentat.engine import Engine
from mentat.logging_config import setup_logging
from mentat.session import Session
from mentat.terminal.prompt_session import MentatPromptSession


class TerminalClient:
    def __init__(self):
        self.engine = Engine()
        self.engine_task: asyncio.Task | None = None

        self._prompt_session = MentatPromptSession(self.engine)

    async def get_user_input(self):
        user_input = await self._prompt_session.prompt_async()

    async def _run(self):
        try:
            self.engine_task = asyncio.create_task(self.engine._run())
            while True:
                user_input = await self.get_user_input()
        except KeyboardInterrupt:
            cprint("keyboard interrupt", color="yellow")
        except Exception as e:
            cprint(f"unhandled exception: {e}", color="red")
        finally:
            if isinstance(self.engine_task, asyncio.Task):
                self.engine._should_exit = True
                assert self.engine_task
                await self.engine_task
                self.engine_task = None

    def run(self):
        asyncio.run(self._run())


if __name__ == "__main__":
    terminal_client = TerminalClient()
    terminal_client.run()
