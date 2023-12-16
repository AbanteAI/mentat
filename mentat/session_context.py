from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

import attr

if TYPE_CHECKING:
    from mentat.agent_handler import AgentHandler
    from mentat.auto_completer import AutoCompleter
    from mentat.code_context import CodeContext
    from mentat.code_file_manager import CodeFileManager
    from mentat.config import Config
    from mentat.conversation import Conversation
    from mentat.cost_tracker import CostTracker
    from mentat.llm_api_handler import LlmApiHandler
    from mentat.sampler.sampler import Sampler
    from mentat.session_stream import SessionStream
    from mentat.vision.vision_manager import VisionManager

SESSION_CONTEXT: ContextVar[SessionContext] = ContextVar("mentat:session_context")


@attr.define()
class SessionContext:
    cwd: Path = attr.field()
    stream: SessionStream = attr.field()
    llm_api_handler: LlmApiHandler = attr.field()
    cost_tracker: CostTracker = attr.field()
    config: Config = attr.field()
    code_context: CodeContext = attr.field()
    code_file_manager: CodeFileManager = attr.field()
    conversation: Conversation = attr.field()
    vision_manager: VisionManager = attr.field()
    agent_handler: AgentHandler = attr.field()
    auto_completer: AutoCompleter = attr.field()
    sampler: Sampler = attr.field()
