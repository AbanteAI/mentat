import gc
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
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as AsyncChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta

from mentat import config
from mentat.agent_handler import AgentHandler
from mentat.auto_completer import AutoCompleter
from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config, config_file_name
from mentat.conversation import Conversation
from mentat.cost_tracker import CostTracker
from mentat.git_handler import get_git_root_for_path
from mentat.llm_api_handler import LlmApiHandler
from mentat.sampler.sampler import Sampler
from mentat.session_context import SESSION_CONTEXT, SessionContext
from mentat.session_stream import SessionStream, StreamMessage, StreamMessageSource
from mentat.streaming_printer import StreamingPrinter
from mentat.vision.vision_manager import VisionManager

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
        "--retries",
        action="store",
        default="1",
        help="Number of times to retry a benchmark",
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


@pytest.fixture(scope="function")
def mock_call_llm_api(mocker):
    completion_mock = mocker.patch.object(LlmApiHandler, "call_llm_api")

    def set_streamed_values(values):
        async def _async_generator():
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
                    model="test-model",
                    object="chat.completion.chunk",
                )

        completion_mock.return_value = _async_generator()

    completion_mock.set_streamed_values = set_streamed_values

    def set_unstreamed_values(value):
        timestamp = int(time.time())
        completion_mock.return_value = ChatCompletion(
            id="test-id",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    message=ChatCompletionMessage(
                        content=value,
                        role="assistant",
                    ),
                )
            ],
            created=timestamp,
            model="test-model",
            object="chat.completion",
        )

    completion_mock.set_unstreamed_values = set_unstreamed_values
    return completion_mock


@pytest.fixture(scope="function")
def mock_call_embedding_api(mocker):
    embedding_mock = mocker.patch.object(LlmApiHandler, "call_embedding_api")

    def set_embedding_values(value):
        embedding_mock.return_value = value

    embedding_mock.set_embedding_values = set_embedding_values
    return embedding_mock


### Auto-used fixtures


@pytest.fixture(autouse=True, scope="function")
def mock_initialize_client(mocker, request):
    if not request.config.getoption("--benchmark"):
        mocker.patch.object(LlmApiHandler, "initialize_client")


# ContextVars need to be set in a synchronous fixture due to pytest not propagating
# async fixture contexts to test contexts.
# https://github.com/pytest-dev/pytest-asyncio/issues/127


@pytest.fixture(autouse=True)
def mock_session_context(temp_testbed):
    """
    This is autoused to make it easier to write tests without having to worry about whether
    or not SessionContext is set; however, this SessionContext will be overwritten by the SessionContext
    set by a Session if the test creates a Session.
    If you create a Session or Client in your test, do NOT use this SessionContext!
    """
    git_root = get_git_root_for_path(temp_testbed, raise_error=False)

    stream = SessionStream()

    cost_tracker = CostTracker()

    config = Config()

    llm_api_handler = LlmApiHandler()

    code_context = CodeContext(stream, git_root)

    code_file_manager = CodeFileManager()
    conversation = Conversation()

    vision_manager = VisionManager()

    agent_handler = AgentHandler()

    auto_completer = AutoCompleter()

    sampler = Sampler()

    session_context = SessionContext(
        Path.cwd(),
        stream,
        llm_api_handler,
        cost_tracker,
        config,
        code_context,
        code_file_manager,
        conversation,
        vision_manager,
        agent_handler,
        auto_completer,
        sampler,
    )
    token = SESSION_CONTEXT.set(session_context)
    yield session_context
    SESSION_CONTEXT.reset(token)


@pytest.fixture
def mock_code_context(temp_testbed, mock_session_context):
    return mock_session_context.code_context


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

    gc.collect()  # Force garbage collection
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
