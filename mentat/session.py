import asyncio
import logging
import shlex
import traceback
from textwrap import dedent
from typing import List
from uuid import uuid4

from .code_change_feedback import get_user_feedback_on_changes
from .code_context import CodeContext
from .code_file_manager import CodeFileManager
from .code_map import CodeMap
from .commands import Command
from .config_manager import ConfigManager
from .git_handler import get_shared_git_root_for_paths
from .llm_api import CostTracker
from .llm_conversation import LLMConversation
from .session_input import collect_user_input
from .session_stream import _SESSION_STREAM, SessionStream

logger = logging.getLogger("mentat.core")
logger.setLevel(logging.DEBUG)


class Session:
    def __init__(
        self,
        paths: List[str] = [],
        exclude_paths: List[str] = [],
        no_code_map: bool = False,
    ):
        self.id = uuid4()
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.no_code_map = no_code_map

        self.stream = SessionStream()
        _SESSION_STREAM.set(self.stream)  # remove?

        self._main_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task | None = None

        git_root = get_shared_git_root_for_paths(self.paths)
        self.config = ConfigManager(git_root)
        self.code_context = CodeContext(
            config=self.config, paths=self.paths, exclude_paths=self.exclude_paths
        )
        self.code_file_manager = CodeFileManager(self.config, self.code_context)
        self.cost_tracker = CostTracker()
        self.code_map = (
            CodeMap(git_root, token_limit=2048) if not self.no_code_map else None
        )

    async def _main(self):
        await self.code_context.display_context()

        if self.code_map is not None:
            await self.code_map.check_ctags_executable()
            if self.code_map.ctags_disabled:
                ctags_disabled_message = f"""
                    There was an error with your universal ctags installation, disabling CodeMap.
                    Reason: {self.code_map.ctags_disabled_reason}
                """
                ctags_disabled_message = dedent(ctags_disabled_message)
                await self.stream.send(ctags_disabled_message, color="yellow")
        llm_conv = await LLMConversation.create(
            self.config, self.cost_tracker, self.code_file_manager, self.code_map
        )

        await self.stream.send(
            "Type 'q' or use Ctrl-C to quit at any time.", color="cyan"
        )
        await self.stream.send("What can I do for you?", color="light_blue")

        need_user_request = True
        while True:
            if need_user_request:
                message = await collect_user_input()

                # Intercept and run command
                if isinstance(message.data, str) and message.data.startswith("/"):
                    arguments = shlex.split(message.data[1:])
                    command = Command.create_command(arguments[0])
                    command.apply(*arguments[1:])
                    continue

                llm_conv.add_user_message(message.data)

            explanation, code_changes = await llm_conv.get_model_response()

            if code_changes:
                need_user_request = await get_user_feedback_on_changes(
                    self.config,
                    llm_conv,
                    self.code_file_manager,
                    code_changes,
                )
            else:
                need_user_request = True

    ### lifecycle

    @property
    def is_stopped(self):
        return self._main_task is None and self._stop_task is None

    def start(self):
        if self._main_task:
            logger.warning("Job already started")
            return

        async def run_main():
            try:
                await self.stream.start()
                _SESSION_STREAM.set(self.stream)
                await self._main()
            except asyncio.CancelledError:
                pass

        def cleanup_main(task: asyncio.Task):
            exception = task.exception()
            if exception is not None:
                logger.error(f"Main task for Session({self.id}) threw an exception")
                traceback.print_exception(
                    type(exception), exception, exception.__traceback__
                )

            self._main_task = None
            logger.debug("Main task stopped")

        self._main_task = asyncio.create_task(run_main())
        self._main_task.add_done_callback(cleanup_main)

    def stop(self):
        if self._stop_task is not None:
            logger.warning("Task is already stopping")
            return
        if self.is_stopped:
            logger.warning("Task is already stopped")
            return

        async def run_stop():
            if self._main_task is None:
                return
            try:
                self._main_task.cancel()
                while self._main_task is not None:
                    await asyncio.sleep(0.1)
                await self.stream.stop()
            except asyncio.CancelledError:
                pass

        def cleanup_stop(_: asyncio.Task):
            self._stop_task = None
            logger.debug("Task has stopped")

        self._stop_task = asyncio.create_task(run_stop())
        self._stop_task.add_done_callback(cleanup_stop)
