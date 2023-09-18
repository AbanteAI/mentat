import asyncio
import logging
from textwrap import dedent
from typing import Iterable

from mentat.session_input_manager import SessionInputManager

from .code_context import CodeContext
from .code_file_manager import CodeFileManager
from .code_map import CodeMap
from .config_manager import ConfigManager
from .git_handler import get_shared_git_root_for_paths
from .llm_api import CostTracker
from .llm_conversation import LLMConversation
from .session_conversation import Message, SessionConversation

logger = logging.getLogger()


class Session:
    def __init__(self):
        self.session_conversation = SessionConversation()
        self.session_input_manager = SessionInputManager(self.session_conversation)

        self._main_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task | None = None

    async def _main(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        cost_tracker: CostTracker,
        no_code_map: bool,
    ):
        git_root = get_shared_git_root_for_paths(paths)
        config = ConfigManager(git_root)
        code_context = CodeContext(
            config, paths, exclude_paths or [], self.session_conversation
        )
        await code_context.display_context()
        code_file_manager = CodeFileManager(
            self.session_conversation, self.session_input_manager, config, code_context
        )
        code_map = CodeMap(git_root, token_limit=2048) if not no_code_map else None
        if code_map is not None and code_map.ctags_disabled:
            ctags_disabled_message = f"""
                There was an error with your universal ctags installation, disabling CodeMap.
                Reason: {code_map.ctags_disabled_reason}
            """
            ctags_disabled_message = dedent(ctags_disabled_message)
            await self.session_conversation.send_message(
                source="server",
                data=dict(content=ctags_disabled_message, color="yellow"),
            )
        conv = LLMConversation(
            config,
            cost_tracker,
            code_file_manager,
            self.session_conversation,
            self.session_input_manager,
            code_map,
        )
        await conv.check_token_limit()

        await self.session_conversation.send_message(
            source="server",
            data=dict(
                content="Type 'q' or use Ctrl-C to quit at any time.", color="cyan"
            ),
        )
        await self.session_conversation.send_message(
            source="server",
            data=dict(content="What can I do for you?", color="light_blue"),
        )

        need_user_request = True
        while True:
            if need_user_request:
                user_response_message = (
                    await self.session_input_manager.collect_user_input()
                )
                assert isinstance(user_response_message, Message)
                user_response = user_response_message.data.get("content")
                conv.add_user_message(user_response)

            explanation, code_changes = await conv.get_model_response(config)

            # if code_changes:
            #     need_user_request = get_user_feedback_on_changes(
            #         config, conv, user_input_manager, code_file_manager, code_changes
            #     )
            # else:
            #     need_user_request = True

    ### lifecycle

    @property
    def is_stopped(self):
        return self._main_task is None and self._stop_task is None

    def start(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str] | None,
        cost_tracker: CostTracker,
        no_code_map: bool,
    ):
        if self._main_task:
            logger.warning("Job already started")
            return

        async def run_main():
            try:
                await self.session_conversation.start()
                await self._main(paths, exclude_paths, cost_tracker, no_code_map)
            except asyncio.CancelledError:
                pass

        def cleanup_main(_: asyncio.Task):
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
                await self.session_conversation.stop()
            except asyncio.CancelledError:
                pass

        def cleanup_stop(_: asyncio.Task):
            self._stop_task = None
            logger.debug("Task has stopped")

        self._stop_task = asyncio.create_task(run_stop())
        self._stop_task.add_done_callback(cleanup_stop)
