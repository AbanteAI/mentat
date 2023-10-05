import asyncio
import logging
import shlex
import traceback
from pathlib import Path
from typing import List, Optional, Union, cast
from uuid import uuid4

from .code_context import CodeContext, CodeContextSettings
from .code_edit_feedback import get_user_feedback_on_edits
from .code_file_manager import CodeFileManager
from .commands import Command
from .config_manager import ConfigManager
from .conversation import Conversation
from .errors import MentatError
from .git_handler import get_shared_git_root_for_paths
from .llm_api import CostTracker, setup_api_key
from .parsers.block_parser import BlockParser
from .parsers.parser import Parser
from .parsers.replacement_parser import ReplacementParser
from .parsers.split_diff_parser import SplitDiffParser
from .session_input import collect_user_input
from .session_stream import SESSION_STREAM, SessionStream

parser_map: dict[str, Parser] = {
    "block": BlockParser(),
    "replacement": ReplacementParser(),
    "split-diff": SplitDiffParser(),
}


class Session:
    def __init__(
        self,
        stream: SessionStream,
        config: ConfigManager,
        parser: Parser,
        code_context_settings: Optional[CodeContextSettings] = None,
    ):
        self.stream = stream
        self.config = config
        self.parser = parser
        self.code_context_settings = code_context_settings or CodeContextSettings()

        self.id = uuid4()
        self.code_file_manager = CodeFileManager(self.config)
        self.cost_tracker = CostTracker()
        setup_api_key()

        self._main_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None

    @classmethod
    async def create(
        cls,
        cwd: Path,
        paths: List[Path] = [],
        exclude_paths: List[Path] = [],
        no_code_map: bool = False,
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
    ):
        stream = SessionStream()
        await stream.start()
        SESSION_STREAM.set(stream)

        git_root = get_shared_git_root_for_paths([Path(path) for path in paths])
        # TODO: Config should be created in the client (i.e., to get vscode settings) and passed to session
        config = await ConfigManager.create(cwd, git_root)
        code_context_settings = CodeContextSettings(
            paths, exclude_paths, diff, pr_diff, no_code_map
        )
        parser = parser_map[config.parser()]

        self = Session(stream, config, parser, code_context_settings)

        return self

    async def _main(self):
        try:
            self.code_context = await CodeContext.create(
                self.config, **self.code_context_settings.asdict()
            )
            await self.code_context.display_context()

            conv = await Conversation.create(
                parser=self.parser,
                config=self.config,
                cost_tracker=self.cost_tracker,
                code_context=self.code_context,
                code_file_manager=self.code_file_manager,
            )
        except MentatError as e:
            await self.stream.send(str(e), color="red")
            return

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
                    command = Command.create_command(arguments[0], self.code_context)
                    await command.apply(*arguments[1:])
                    continue

                if message.data == "q":
                    break

                conv.add_user_message(message.data)

            file_edits = await conv.get_model_response(self.parser, self.config)
            file_edits = [
                file_edit
                for file_edit in file_edits
                if await file_edit.is_valid(self.code_file_manager, self.config)
            ]
            if file_edits:
                need_user_request = await get_user_feedback_on_edits(
                    config=self.config,
                    conv=conv,
                    code_file_manager=self.code_file_manager,
                    code_context=self.code_context,
                    file_edits=file_edits,
                )
            else:
                need_user_request = True

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
            if self._main_task is None:
                return
            try:
                await self.cost_tracker.display_total_cost()
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
