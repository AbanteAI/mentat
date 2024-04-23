import gc
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from spice import SpiceResponse
from spice.spice import SpiceCallArgs

from mentat import config
from mentat.agent_handler import AgentHandler
from mentat.auto_completer import AutoCompleter
from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config, config_file_name
from mentat.conversation import Conversation
from mentat.llm_api_handler import LlmApiHandler
from mentat.parsers.streaming_printer import StreamingPrinter
from mentat.sampler.sampler import Sampler
from mentat.session_context import SESSION_CONTEXT, SessionContext
from mentat.session_stream import SessionStream, StreamMessage, StreamMessageSource
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


@pytest.fixture
def benchmarks(request):
    benchmarks = request.config.getoption("--benchmarks")
    if len(benchmarks) == 1:
        return benchmarks[0]
    return benchmarks


def pytest_configure(config):
    config.addinivalue_line("markers", "benchmark: run benchmarks that call openai")
    config.addinivalue_line("markers", "uitest: run ui-tests that get evaluated by humans")
    config.addinivalue_line("markers", "clear_testbed: create a testbed without any existing files")
    config.addinivalue_line("markers", "no_git_testbed: create a testbed without git")
    config.addinivalue_line("markers", "ragdaemon: DON'T mock the daemon in the testbed")


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
            )
            for value in values
        ]

    async_mock.set_stream_messages = set_stream_messages
    return async_mock


@pytest.fixture(scope="function")
def mock_call_llm_api(mocker):
    completion_mock = mocker.patch.object(LlmApiHandler, "call_llm_api")

    def wrap_unstreamed_string(value):
        return SpiceResponse(SpiceCallArgs("gpt-3.5-turbo", [], False), value, 1, 0, 0, True, 1)

    def wrap_streamed_strings(values):
        class MockStreamingSpiceResponse:
            def __init__(self):
                self.cur_value = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.cur_value >= len(values):
                    raise StopAsyncIteration
                self.cur_value += 1
                return values[self.cur_value - 1]

            def current_response(self):
                return SpiceResponse(SpiceCallArgs("gpt-3.5-turbo", [], True), "".join(values), 1, 0, 0, True, 1)

        mock_spice_response = MockStreamingSpiceResponse()
        return mock_spice_response

    def set_streamed_values(values):
        completion_mock.return_value = wrap_streamed_strings(values)

    completion_mock.set_streamed_values = set_streamed_values

    def set_unstreamed_values(value):
        completion_mock.return_value = wrap_unstreamed_string(value)

    completion_mock.set_unstreamed_values = set_unstreamed_values

    def set_return_values(values):
        async def call_llm_api_mock(messages, model, provider, stream, response_format="unused"):
            value = call_llm_api_mock.values.pop()
            if stream:
                return wrap_streamed_strings([value])
            else:
                return wrap_unstreamed_string(value)

        call_llm_api_mock.values = values[::-1]
        completion_mock.side_effect = call_llm_api_mock

    completion_mock.set_return_values = set_return_values

    return completion_mock


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
    stream = SessionStream()

    config = Config()

    llm_api_handler = LlmApiHandler()

    code_context = CodeContext(stream, temp_testbed)

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

    If the error is because the file is being used by another process,
    it retries after a short delay.

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
def temp_testbed(mocker, monkeypatch, get_marks):
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

    if "ragdaemon" not in get_marks:
        mocker.patch("ragdaemon.daemon.Daemon.update", side_effect=AsyncMock())

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
def mock_api_key():
    os.environ["OPENAI_API_KEY"] = "fake_testing_key"
