import asyncio
import logging
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
from mentat.errors import MentatError, SessionExit
from mentat.git_handler import get_shared_git_root_for_paths
from mentat.llm_api import CostTracker, setup_api_key
from mentat.logging_config import setup_logging
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.parser import Parser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.parsers.split_diff_parser import SplitDiffParser
from mentat.parsers.unified_diff_parser import UnifiedDiffParser
from mentat.session_context import SESSION_CONTEXT, SessionContext
from mentat.session_input import collect_user_input
from mentat.session_stream import SessionStream

parser_map: dict[str, Parser] = {
    "block": BlockParser(),
    "replacement": ReplacementParser(),
    "split-diff": SplitDiffParser(),
    "unified-diff": UnifiedDiffParser(),
}


class Session:
    def __init__(
        self,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        ignore_paths: List[Path] = [],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        config: Config = Config(),
    ):
        self.id = uuid4()
        setup_api_key()

        # Since we can't set the session_context until after all of the singletons are created,
        # any singletons used in the constructor of another singleton must be passed in
        git_root = get_shared_git_root_for_paths([Path(path) for path in paths])

        stream = SessionStream()
        stream.start()
        self.stream = stream

        cost_tracker = CostTracker()

        parser = parser_map[config.format]

        code_context = CodeContext(stream, git_root, diff, pr_diff)

        code_file_manager = CodeFileManager()

        conversation = Conversation(parser)

        session_context = SessionContext(
            stream,
            cost_tracker,
            git_root,
            config,
            parser,
            code_context,
            code_file_manager,
            conversation,
        )
        SESSION_CONTEXT.set(session_context)

        # Functions that require session_context
        config.send_errors_to_stream()
        code_context.set_paths(paths, exclude_paths, ignore_paths)
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
                file_edits = [
                    file_edit for file_edit in file_edits if file_edit.is_valid()
                ]
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
