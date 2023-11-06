import asyncio
import logging
import subprocess
from asyncio import Task
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from openai.error import RateLimitError, Timeout

from mentat.code_context import CodeContext
from mentat.code_edit_feedback import get_user_feedback_on_edits
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config
from mentat.conversation import Conversation
from mentat.diff_context import DiffContext
from mentat.errors import MentatError, SessionExit, UserError
from mentat.git_handler import get_shared_git_root_for_paths
from mentat.llm_api import CostTracker, setup_api_key
from mentat.logging_config import setup_logging
from mentat.parsers.parser_map import parser_map
from mentat.session_context import SESSION_CONTEXT, SessionContext
from mentat.session_input import collect_user_input
from mentat.session_stream import SessionStream


class Session:
    def __init__(
        self,
        cwd: Path,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        ignore_paths: List[Path] = [],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        config: Config = Config(),
    ):
        self.id = uuid4()
        setup_api_key()

        self.stream = SessionStream()
        self.stream.start()

        cost_tracker = CostTracker()

        parser = parser_map[config.format]

        try:
            git_root = get_shared_git_root_for_paths(paths)
            diff_context = DiffContext(self.stream, git_root, diff, pr_diff)
        except (UserError, subprocess.CalledProcessError):
            diff_context = None
        code_context = CodeContext(ignore_paths, diff_context)

        code_file_manager = CodeFileManager()

        conversation = Conversation(parser)

        session_context = SessionContext(
            self.stream,
            cost_tracker,
            cwd,
            config,
            parser,
            code_context,
            code_file_manager,
            conversation,
        )
        SESSION_CONTEXT.set(session_context)

        # Functions that require session_context
        config.send_errors_to_stream()
        for path in paths:
            code_context.include(path, exclude_paths)
        code_context.set_code_map()

    async def _main(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        conversation = session_context.conversation

        try:
            code_context.display_context()
            await conversation.display_token_count()
        except MentatError as e:
            stream.send(str(e), color="red")
            return

        try:
            stream.send("Type 'q' or use Ctrl-C to quit at any time.", color="cyan")
            stream.send("What can I do for you?", color="light_blue")
            need_user_request = True
            while True:
                if need_user_request:
                    message = await collect_user_input()
                    if message.data.strip() == "":
                        continue
                    conversation.add_user_message(message.data)

                file_edits = await conversation.get_model_response()
                file_edits = [file_edit for file_edit in file_edits if file_edit.is_valid()]
                if file_edits:
                    need_user_request = await get_user_feedback_on_edits(file_edits)
                else:
                    need_user_request = True
                stream.send(bool(file_edits), channel="edits_complete")
        except SessionExit:
            pass
        except (Timeout, RateLimitError) as e:
            stream.send(f"Error accessing OpenAI API: {str(e)}", color="red")

    ### lifecycle

    def start(self) -> asyncio.Task[None]:
        """Asynchronously start the Session.

        A background asyncio Task will be created to run the startup sequence and run
        the main loop which runs forever (until a client interrupts it).
        """

        async def run_main():
            try:
                await self._main()
                await self.stop()
            except asyncio.CancelledError:
                pass

        setup_logging()
        self._main_task: Task[None] = asyncio.create_task(run_main())
        return self._main_task

    async def stop(self):
        session_context = SESSION_CONTEXT.get()
        cost_tracker = session_context.cost_tracker

        cost_tracker.display_total_cost()
        logging.shutdown()
        self._main_task.cancel()
        await self._main_task
        self.stream.send(None, channel="exit")
        await self.stream.join()
        self.stream.stop()
