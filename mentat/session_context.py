from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

import attr

from mentat.git_handler import get_shared_git_root_for_paths

if TYPE_CHECKING:
    from mentat.code_context import CodeContext, CodeContextSettings
    from mentat.code_file_manager import CodeFileManager
    from mentat.config_manager import ConfigManager
    from mentat.conversation import Conversation
    from mentat.llm_api import CostTracker
    from mentat.parsers.parser import Parser
    from mentat.session_stream import SessionStream

SESSION_CONTEXT: ContextVar[SessionContext] = ContextVar("mentat:session_context")


@attr.define()
class SessionContext:
    stream: SessionStream = attr.field()
    cost_tracker: CostTracker = attr.field()
    git_root: Path = attr.field()
    config: ConfigManager = attr.field()
    parser: Parser = attr.field()
    code_context: CodeContext = attr.field()
    code_file_manager: CodeFileManager = attr.field()
    conversation: Conversation = attr.field()

    # Override the attr default constructor
    def __init__(self):
        pass

    @classmethod
    async def create(
        cls,
        paths: list[Path],
        exclude_paths: list[Path],
        code_context_settings: CodeContextSettings,
    ):
        from mentat.session import parser_map

        self = cls()
        SESSION_CONTEXT.set(self)

        self.stream = SessionStream()
        await self.stream.start()

        self.cost_tracker = CostTracker()

        self.git_root = get_shared_git_root_for_paths([Path(path) for path in paths])

        # TODO: Part of config should be retrieved in client (i.e., to get vscode settings) and passed to server
        self.config = await ConfigManager.create()

        self.parser = parser_map[self.config.parser()]

        self.code_context = await CodeContext.create(
            paths, exclude_paths, code_context_settings
        )

        self.code_file_manager = CodeFileManager()

        self.conversation = Conversation()

        return self
