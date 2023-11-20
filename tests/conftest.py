import os
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as AsyncChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from mentat import config
from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config, config_file_name
from mentat.conversation import Conversation
from mentat.cost_tracker import CostTracker
from mentat.session_context import SESSION_CONTEXT, SessionContext
from mentat.session_stream import SessionStream, StreamMessage, StreamMessageSource
from mentat.streaming_printer import StreamingPrinter

pytest_plugins = ("pytest_reportlog",)


def filter_mark(items, mark, exists):
    new_items = []
    for item in items:
        marker = item.get_closest_marker(mark)
        if bool(marker) == bool(exists):
            new_items.append(item)
    return new_items


def pytest_addoption(parser):
    parser.addoption("--benchmark", action="store_true")
    parser.addoption("--uitest", action="store_true")
    # The following flags are used by benchmark tests
    parser.addoption(
        "--max_benchmarks",
        action="store",
        default="1",
        help="The maximum number of exercises to run",
    )
    parser.addoption(
        "--max_iterations",
        action="store",
        default="1",
        help="Number of times to rerun mentat with error messages",
    )
    parser.addoption(
        "--language",
        action="store",
        default="python",
        help="Which exercism language to do exercises for",
    )
    parser.addoption(
        "--max_workers",
        action="store",
        default="1",
        help="Number of workers to use for multiprocessing",
    )
    parser.addoption(
        "--refresh_repo",
        action="store_true",
        default=False,
        help="When set local changes will be discarded.",
    )
    parser.addoption(
        "--benchmarks",
        action="append",
        nargs="*",
        default=[],
        help=(
            "Which benchmarks to run. max_benchmarks ignored when set. Exact meaning"
            " depends on benchmark."
        ),
    )
    parser.addoption(
        "--repo",
        action="store",
        default="mentat",
        help="For benchmarks that are evaluated against a repo",
    )
    parser.addoption(
        "--evaluate_baseline",
        action="store_true",
        help="Evaluate the baseline for the benchmark",
    )


@pytest.fixture
def refresh_repo(request):
    return request.config.getoption("--refresh_repo")


@pytest.fixture
def benchmarks(request):
    benchmarks = request.config.getoption("--benchmarks")
    if len(benchmarks) == 1:
        return benchmarks[0]
    return benchmarks


@pytest.fixture
def max_benchmarks(request):
    return int(request.config.getoption("--max_benchmarks"))


def pytest_configure(config):
    config.addinivalue_line("markers", "benchmark: run benchmarks that call openai")
    config.addinivalue_line(
        "markers", "uitest: run ui-tests that get evaluated by humans"
    )
    config.addinivalue_line(
        "markers", "clear_testbed: create a testbed without any existing files"
    )
    config.addinivalue_line("markers", "no_git_testbed: create a testbed without git")


def pytest_collection_modifyitems(config, items):
    benchmark = config.getoption("--benchmark")
    uitest = config.getoption("--uitest")
    items[:] = filter_mark(items, "benchmark", benchmark)
    items[:] = filter_mark(items, "uitest", uitest)


@pytest.fixture
def get_marks(request):
    return [mark.name for mark in request.node.iter_markers()]


@pytest.fixture
def mock_collect_user_input(mocker):
    async_mock = AsyncMock()

    mocker.patch("mentat.session_input._get_input_request", side_effect=async_mock)

    def set_stream_messages(values):
        async_mock.side_effect = [
            StreamMessage(
                id=uuid4(),
                channel="default",
                source=StreamMessageSource.CLIENT,
                data=value,
                extra={},
                created_at=datetime.utcnow(),
            )
            for value in values
        ]

    async_mock.set_stream_messages = set_stream_messages
    return async_mock


class MockLlmApiHandler:
    def __init__(self, config):
        self.streamed_values = []
        self.unstreamed_value = ""
        self.embeddings = []
        self.models_available = set([config.model])
        self.llm_call_args = tuple()
        self.embeddings_call_args = tuple()

    async def _async_generator(self, values: list[str], model: str):
        timestamp = int(time.time())
        for value in values:
            yield ChatCompletionChunk(
                id="test-id",
                choices=[
                    AsyncChoice(
                        delta=ChoiceDelta(content=value, role="assistant"),
                        finish_reason=None,
                        index=0,
                    )
                ],
                created=timestamp,
                model=model,
                object="chat.completion.chunk",
            )

    async def call_llm_api(
        self, messages: list[ChatCompletionMessageParam], model: str, stream: bool
    ):
        self.llm_call_args = (messages, model, stream)
        if stream:
            return self._async_generator(self.streamed_values, model)
        else:
            timestamp = int(time.time())
            return ChatCompletion(
                id="test-id",
                choices=[
                    Choice(
                        finish_reason="stop",
                        index=0,
                        message=ChatCompletionMessage(
                            content=self.unstreamed_value,
                            role="assistant",
                        ),
                    )
                ],
                created=timestamp,
                model=model,
                object="chat.completion",
            )

    async def call_embedding_api(
        self, input_texts: list[str], model: str = "text-embedding-ada-002"
    ):
        self.embeddings_call_args = (input_texts, model)
        return self.embeddings

    async def is_model_available(self, model: str) -> bool:
        return model in self.models_available


# ContextVars need to be set in a synchronous fixture due to pytest not propagating
# async fixture contexts to test contexts.
# https://github.com/pytest-dev/pytest-asyncio/issues/127


@pytest.fixture(autouse=True)
def mock_session_context(temp_testbed):
    # TODO make this `None` if there's no git (SessionContext needs to allow it)
    git_root = temp_testbed

    stream = SessionStream()

    cost_tracker = CostTracker()

    config = Config()

    llm_api_handler = MockLlmApiHandler(config)

    code_context = CodeContext(stream, git_root)

    code_file_manager = CodeFileManager()

    conversation = Conversation()

    session_context = SessionContext(
        stream,
        llm_api_handler,
        cost_tracker,
        git_root,
        config,
        code_context,
        code_file_manager,
        conversation,
    )
    token = SESSION_CONTEXT.set(session_context)
    yield session_context
    SESSION_CONTEXT.reset(token)


### Auto-used fixtures


def run_git_command(cwd, *args):
    """Helper function to run a git command."""
    subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def add_permissions(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.
    """

    # Is the error an access error?
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


@pytest.fixture(autouse=True)
def temp_testbed(monkeypatch, get_marks):
    # Allow us to run tests from any directory
    base_dir = Path(__file__).parent.parent

    # create temporary copy of testbed, complete with git repo
    # realpath() resolves symlinks, required for paths to match on macOS
    temp_dir = os.path.realpath(tempfile.mkdtemp())
    temp_testbed = os.path.join(temp_dir, "testbed")
    os.mkdir(temp_testbed)

    if "no_git_testbed" not in get_marks:
        # Initialize git repo
        run_git_command(temp_testbed, "init")

        # Set local config for user.name and user.email. Set automatically on
        # MacOS, but not Windows/Ubuntu, which prevents commits from taking.
        run_git_command(temp_testbed, "config", "user.email", "test@example.com")
        run_git_command(temp_testbed, "config", "user.name", "Test User")

    if "clear_testbed" not in get_marks:
        # Copy testbed
        shutil.copytree(base_dir / "testbed", temp_testbed, dirs_exist_ok=True)
        shutil.copy(base_dir / ".gitignore", temp_testbed)

        if "no_git_testbed" not in get_marks:
            # Add all files and commit
            run_git_command(temp_testbed, "add", ".")
            run_git_command(temp_testbed, "commit", "-m", "add testbed")

    # necessary to undo chdir before calling rmtree, or it fails on windows
    with monkeypatch.context() as m:
        m.chdir(temp_testbed)
        yield Path(temp_testbed)

    shutil.rmtree(temp_dir, onerror=add_permissions)


# Always set the user config to just be a config in the temp_testbed; that way,
# it will be unset unless a specific test wants to make a config in the testbed
@pytest.fixture(autouse=True)
def mock_user_config(mocker):
    config.user_config_path = Path(config_file_name)


@pytest.fixture(autouse=True)
def mock_sleep_time(mocker):
    mocker.patch.object(StreamingPrinter, "sleep_time", new=lambda self: 0)


@pytest.fixture(autouse=True)
def mock_get_codemaps(mocker):
    mocker.patch("mentat.code_map.get_code_map", return_value=[])
