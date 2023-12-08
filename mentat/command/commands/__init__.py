# ruff: noqa: F401
# type: ignore

# Import all of the commands so that they are initialized
from .agent import AgentCommand
from .clear import ClearCommand
from .commit import CommitCommand
from .config import ConfigCommand
from .context import ContextCommand
from .conversation import ConversationCommand
from .exclude import ExcludeCommand
from .help import HelpCommand
from .include import IncludeCommand
from .redo import RedoCommand
from .run import RunCommand
from .screenshot import ScreenshotCommand
from .search import SearchCommand
from .talk import TalkCommand
from .undo import UndoCommand
from .undoall import UndoAllCommand
