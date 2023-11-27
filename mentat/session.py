import asyncio
import logging
import os
import traceback
from asyncio import CancelledError, Task
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import attr
import sentry_sdk
from openai import APITimeoutError, BadRequestError, RateLimitError

from mentat.code_context import CodeContext
from mentat.code_edit_feedback import get_user_feedback_on_edits
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config
from mentat.conversation import Conversation
from mentat.cost_tracker import CostTracker
from mentat.errors import MentatError, SessionExit, UserError
from mentat.git_handler import get_shared_git_root_for_paths
from mentat.llm_api_handler import LlmApiHandler, is_test_environment
from mentat.logging_config import setup_logging
from mentat.sentry import sentry_init
from mentat.session_context import SESSION_CONTEXT, SessionContext
from mentat.session_input import collect_user_input
from mentat.session_stream import SessionStream
from mentat.utils import check_version, mentat_dir_path


class Session:
    """
    The server for Mentat.
    To stop, send a message on the session_exit channel.
    A message will be sent on the client_exit channel when ready for client to quit.
    """

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
        # TODO: All errors should be thrown in _main, and should never be thrown here
        self.stopped = False

        if not mentat_dir_path.exists():
            os.mkdir(mentat_dir_path)
        setup_logging()
        sentry_init()
        self.id = uuid4()

        # Since we can't set the session_context until after all of the singletons are created,
        # any singletons used in the constructor of another singleton must be passed in
        git_root = get_shared_git_root_for_paths([Path(path) for path in paths])

        llm_api_handler = LlmApiHandler()

        stream = SessionStream()
        self.stream = stream
        self.stream.start()

        cost_tracker = CostTracker()

        code_context = CodeContext(stream, git_root, diff, pr_diff)

        code_file_manager = CodeFileManager()

        conversation = Conversation()

        session_context = SessionContext(
            cwd,
            stream,
            llm_api_handler,
            cost_tracker,
            git_root,
            config,
            code_context,
            code_file_manager,
            conversation,
        )
        SESSION_CONTEXT.set(session_context)

        # Functions that require session_context
        check_version()
        config.send_errors_to_stream()
        code_context.set_paths(paths, exclude_paths, ignore_paths)

    async def _main(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        conversation = session_context.conversation
        llm_api_handler = session_context.llm_api_handler

        llm_api_handler.initizalize_client()
        code_context.display_context()
        await conversation.display_token_count()

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
        except (APITimeoutError, RateLimitError, BadRequestError) as e:
            stream.send(f"Error accessing OpenAI API: {str(e)}", color="red")

    async def listen_for_session_exit(self):
        await self.stream.recv(channel="session_exit")
        self._main_task.cancel()

    ### lifecycle

    def start(self):
        """Asynchronously start the Session.

        A background asyncio Task will be created to run the startup sequence and run
        the main loop which runs until an Exception or session_exit signal is encountered.
        """

        async def run_main():
            ctx = SESSION_CONTEXT.get()
            try:
                with sentry_sdk.start_transaction(
                    op="mentat_started", name="Mentat Started"
                ) as transaction:
                    transaction.set_tag("config", attr.asdict(ctx.config))
                    await self._main()
            except (SessionExit, CancelledError):
                pass
            except (MentatError, UserError) as e:
                self.stream.send(str(e), color="red")
            except Exception as e:
                # All unhandled exceptions end up here
                error = f"Unhandled Exception: {traceback.format_exc()}"
                # Helps us handle errors in tests
                if is_test_environment():
                    print(error)
                sentry_sdk.capture_exception(e)
                self.stream.send(error, color="red")
            finally:
                await self._stop()
                sentry_sdk.flush()

        self._main_task: Task[None] = asyncio.create_task(run_main())
        # If we create more tasks in Session, add a task list and helper function like we have in TerminalClient
        self._exit_task: Task[None] = asyncio.create_task(
            self.listen_for_session_exit()
        )

    async def _stop(self):
        if self.stopped:
            return
        self.stopped = True

        session_context = SESSION_CONTEXT.get()
        cost_tracker = session_context.cost_tracker

        cost_tracker.display_total_cost()
        logging.shutdown()
        self._exit_task.cancel()
        self._main_task.cancel()
        try:
            await self._main_task
        except CancelledError:
            pass
        self.stream.send(None, channel="client_exit")
        await self.stream.join()
        self.stream.stop()
