import asyncio
import logging

from mentat.engine import MentatEngine
from mentat.logging_config import setup_logging
from mentat.terminal.logging_handers import ConsoleHandler
from mentat.terminal.prompt_session import MentatPromptSession

# from .logging_handers import ConsoleHandler
# from .prompt_session import MentatPromptSession


class TerminalClient:
    def __init__(self):
        self._engine = MentatEngine()
        self._engine_task = None

        self._session = MentatPromptSession(self._engine)

    async def get_user_input(self):
        user_input = await self._session.prompt_async()

    async def _run(self):
        try:
            self._engine_task = asyncio.create_task(self._engine._run())
            while True:
                await self.get_user_input()
        except KeyboardInterrupt:
            print("keyboard interrupt")
        except Exception as e:
            print("unhandled exception:", e)
        finally:
            if isinstance(self._engine_task, asyncio.Task):
                self._engine._should_exit = True
                assert self._engine_task
                await self._engine_task
                self._engine_task = None

    def run(self):
        asyncio.run(self._run())


if __name__ == "__main__":
    terminal_client = TerminalClient()
    terminal_client.run()
