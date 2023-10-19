import asyncio
import logging
import traceback
from pathlib import Path
from typing import List, Optional, Union, cast
from uuid import uuid4

from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.conversation import Conversation
from mentat.git_handler import get_shared_git_root_for_paths
from mentat.logging_config import setup_logging
from mentat.session_context import SESSION_CONTEXT, SessionContext

from .code_context import CodeContext, CodeContextSettings
from .code_edit_feedback import get_user_feedback_on_edits
from .errors import MentatError, SessionExit
from .llm_api import CostTracker, setup_api_key
from .parsers.block_parser import BlockParser
from .parsers.parser import Parser
from .parsers.replacement_parser import ReplacementParser
from .parsers.split_diff_parser import SplitDiffParser
from .parsers.unified_diff_parser import UnifiedDiffParser
from .session_input import collect_user_input
from .session_stream import SessionStream

parser_map: dict[str, Parser] = {
    "block": BlockParser(),
    "replacement": ReplacementParser(),
    "split-diff": SplitDiffParser(),
    "unified-diff": UnifiedDiffParser(),
}


class Session:
    def __init__(
        self,
        stream: SessionStream,
    ):
        self.stream = stream

        self.id = uuid4()
        setup_api_key()

        self._main_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None

    @classmethod
    async def create(
        cls,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        no_code_map: bool = False,
        use_embedding: bool = False,
        auto_tokens: Optional[int] = None,
    ):
        # Since we can't set the session_context until after all of the singletons are created,
        # any singletons used in the constructor of another singleton must be passed in
        git_root = get_shared_git_root_for_paths([Path(path) for path in paths])

        stream = SessionStream()
        await stream.start()

        cost_tracker = CostTracker()

        # TODO: Part of config should be retrieved in client (i.e., to get vscode settings) and passed to server
        config = await ConfigManager.create(git_root, stream)

        parser = parser_map[config.parser()]

        code_context_settings = CodeContextSettings(
            diff, pr_diff, no_code_map, use_embedding, auto_tokens
        )
        code_context = await CodeContext.create(stream, git_root, code_context_settings)

        code_file_manager = CodeFileManager()

        conversation = Conversation(config, parser)

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

        # Functions that require session_context
        await code_context.set_paths(paths, exclude_paths)

        return cls(session_context.stream)

    async def _main(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        conversation = session_context.conversation

        try:
            await code_context.display_context()
            await conversation.display_token_count()
        except MentatError as e:
            await stream.send(str(e), color="red")
            return

        try:
            await stream.send(
                "Type 'q' or use Ctrl-C to quit at any time.", color="cyan"
            )
            await stream.send("What can I do for you?", color="light_blue")
            need_user_request = True
            while True:
                if need_user_request:
                    message = await collect_user_input()
                    if message.data.strip() == "":
                        continue
                    conversation.add_user_message(message.data)

                file_edits = await conversation.get_model_response()
                file_edits = [
                    file_edit for file_edit in file_edits if await file_edit.is_valid()
                ]
                if file_edits:
                    need_user_request = await get_user_feedback_on_edits(file_edits)
                else:
                    need_user_request = True
        except SessionExit:
            pass

    ### lifecycle

    @property
    def is_stopped(self):
        return self._main_task is None and self._stop_task is None

    def start(self) -> asyncio.Task[None]:
        """Asynchronously start the Session.

        A background asyncio. Task will be created to run the startup sequence and run
        the main loop which runs forever (until a client interrupts it).
        """

        if self._main_task:
            logging.warning("Job already started")
            return self._main_task

        setup_logging()

        async def run_main():
            try:
                await self._main()
                await cast(asyncio.Task[None], self.stop())
            except asyncio.CancelledError:
                pass

        def cleanup_main(task: asyncio.Task[None]):
            exception = task.exception()
            if exception is not None:
                logging.error(f"Main task for Session({self.id}) threw an exception")
                traceback.print_exception(
                    type(exception), exception, exception.__traceback__
                )

            self._main_task = None
            logging.debug("Main task stopped")

        self._main_task = asyncio.create_task(run_main())
        self._main_task.add_done_callback(cleanup_main)

        return self._main_task

    def stop(self) -> asyncio.Task[None] | None:
        """Asynchronously stop the Session.

        A background asyncio.Task will be created that handles the shutdown sequence
        of the Session. Clients should wait for `self.is_stopped` to return `True` in
        order to make sure the shutdown sequence has finished.
        """
        if self._stop_task is not None:
            logging.debug("Task is already stopping")
            return self._stop_task
        if self.is_stopped:
            logging.debug("Task is already stopped")
            return

        async def run_stop():
            session_context = SESSION_CONTEXT.get()
            cost_tracker = session_context.cost_tracker

            if self._main_task is None:
                return
            try:
                await cost_tracker.display_total_cost()
                logging.shutdown()
                self._main_task.cancel()

                # Pyright can't see `self._main_task` being set to `None` in the task
                # callback handler, so we have to cast the type explicitly here
                self._main_task = cast(Union[asyncio.Task[None], None], self._main_task)

                while self._main_task is not None:
                    await asyncio.sleep(0.01)
                await self.stream.stop()
            except asyncio.CancelledError:
                pass

        def cleanup_stop(_: asyncio.Task[None]):
            self._stop_task = None
            logging.debug("Task has stopped")

        self._stop_task = asyncio.create_task(run_stop())
        self._stop_task.add_done_callback(cleanup_stop)

        return self._stop_task
