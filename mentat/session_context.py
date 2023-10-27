from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

import attr

if TYPE_CHECKING:
    from mentat.code_context import CodeContext
    from mentat.code_file_manager import CodeFileManager
    from mentat.config import Config
    from mentat.conversation import Conversation
    from mentat.llm_api import CostTracker
    from mentat.session_stream import SessionStream

SESSION_CONTEXT: ContextVar[SessionContext] = ContextVar("mentat:session_context")


@attr.define()
class SessionContext:
    stream: SessionStream = attr.field()
    cost_tracker: CostTracker = attr.field()
    git_root: Path = attr.field()
    config: Config = attr.field()
    code_context: CodeContext = attr.field()
    code_file_manager: CodeFileManager = attr.field()
    conversation: Conversation = attr.field()
