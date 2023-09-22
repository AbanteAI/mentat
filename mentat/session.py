import asyncio
import logging
import shlex
import traceback
from datetime import datetime
from textwrap import dedent
from typing import Any, AsyncGenerator, Dict, Iterable, List, Literal
from uuid import uuid4

from .broadcast import Broadcast
from .code_change import CodeChange
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

logger = logging.getLogger()


class Session:
    def __init__(
        self,
        paths: List[str] | None = None,
        exclude_paths: List[str] | None = None,
        no_code_map: bool = False,
    ):
        self.id = uuid4()

        self.git_root = get_shared_git_root_for_paths(paths)
        self.config = ConfigManager(self.git_root)
        self.code_context = CodeContext(
            config=self.config, paths=paths or [], exclude_paths=exclude_paths or []
        )
        self.code_file_manager = CodeFileManager(self.config, self.code_context)
        self.cost_tracker = CostTracker()
        self.code_map = (
            CodeMap(self.git_root, token_limit=2048) if not no_code_map else None
        )
        self.stream = SessionStream()

        self._main_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task | None = None

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
                self.stream.send(ctags_disabled_message, color="yellow")
        llm_conv = await LLMConversation.create(
            self.config, self.cost_tracker, self.code_file_manager, self.code_map
        )

        self.stream.send("Type 'q' or use Ctrl-C to quit at any time.", color="cyan")
        self.stream.send("What can I do for you?", color="light_blue")

        need_user_request = True
        while True:
            if need_user_request:
                user_response_message = await collect_user_input()
                user_response = user_response_message.data.get("content")

                # Intercept and run command
                if isinstance(user_response, str) and user_response.startswith("/"):
                    arguments = shlex.split(user_response[1:])
                    command = Command.create_command(arguments[0])
                    command.apply(*arguments[1:])
                    continue

                llm_conv.add_user_message(user_response)

            explanation, code_changes = await llm_conv.get_model_response()

            # if code_changes:
            #     need_user_request = get_user_feedback_on_changes(
            #         config,
            #         llm_conv,
            #         user_input_manager,
            #         code_file_manager,
            #         code_changes,
            #     )
            # else:
            #     need_user_request = True

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
            # Shutdown everything on exception?
            exception = task.exception()
            if exception is not None:
                # logger.exception("Main task threw an exception", exception)
                logger.error(f"Main task for Session({self.id}) threw an exception")
                traceback.print_exception(
                    type(exception), exception, exception.__traceback__
                )

            # set_trace()
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


# async def get_user_feedback_on_changes(
#     config: ConfigManager,
#     conv: LLMConversation,
#     code_file_manager: CodeFileManager,
#     code_changes: Iterable[CodeChange],
# ):
#     session_conversation = get_session_conversation()
#
#     await session_conversation.send_message(
#         dict(
#             content="Apply these changes? 'Y/n/i' or provide feedback.",
#             color="light_blue",
#         )
#     )
#     async with listen_for_interrupt
