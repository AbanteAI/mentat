import asyncio
import logging

from core import MentatEngine
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completion, WordCompleter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


class TerminalCompleter(WordCompleter):
    def __init__(self, engine: MentatEngine):
        self.engine = engine

    async def get_completions_async(self, document, complete_event):
        document_words = document.text_before_cursor.split()
        if not document_words:
            return
        last_word = document_words[-1]
        completions = await self.engine.completer.get_completions(last_word)
        for completion in completions:
            yield Completion(completion.data, display=completion.data)


class TerminalClient:
    def __init__(self):
        self._engine = MentatEngine()
        self._engine_task = None

        self._session = PromptSession(completer=TerminalCompleter(self._engine))

    async def get_user_input(self):
        if self._session is None:
            raise Exception("TerminalClient not started")

        print("input something:\n")
        user_input = await self._session.prompt_async()
        print("User input:", user_input)

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
