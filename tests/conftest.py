import os
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from mentat import config_manager
from mentat.code_context import CODE_CONTEXT, CodeContext, CodeContextSettings
from mentat.code_file_manager import CODE_FILE_MANAGER, CodeFileManager
from mentat.config_manager import CONFIG_MANAGER, ConfigManager, config_file_name
from mentat.git_handler import GIT_ROOT
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.parser import PARSER
from mentat.session_stream import (
    SESSION_STREAM,
    SessionStream,
    StreamMessage,
    StreamMessageSource,
)
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
        "--max_exercises",
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
        "--exercises",
        action="append",
        nargs="*",
        default=[],
        help="Which exercism exercises to run. max_exercises ignored when set.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "benchmark: run benchmarks that call openai")
    config.addinivalue_line(
        "markers", "uitest: run ui-tests that get evaluated by humans"
    )


def pytest_collection_modifyitems(config, items):
    benchmark = config.getoption("--benchmark")
    uitest = config.getoption("--uitest")
    items[:] = filter_mark(items, "benchmark", benchmark)
    items[:] = filter_mark(items, "uitest", uitest)


@pytest.fixture(scope="function")
def mock_call_llm_api(mocker):
    mock = mocker.patch("mentat.conversation.call_llm_api")

    def set_generator_values(values):
        async def async_generator():
            for value in values:
                yield {"choices": [{"delta": {"content": value}}]}
            yield {"choices": [{"delta": {"content": "\n"}}]}

        mock.return_value = async_generator()

    mock.set_generator_values = set_generator_values

    return mock


@pytest.fixture
def mock_collect_user_input(mocker):
    async_mock = AsyncMock()

    mocker.patch("mentat.code_edit_feedback.collect_user_input", side_effect=async_mock)
    mocker.patch("mentat.session_input.collect_user_input", side_effect=async_mock)
    mocker.patch("mentat.session.collect_user_input", side_effect=async_mock)

    def set_stream_messages(values):
        async_mock.side_effect = [
            StreamMessage(
                id=uuid4(),
                channel="default",
                source=StreamMessageSource.CLIENT,
                data=value,
                extra=None,
                created_at=datetime.utcnow(),
            )
            for value in values
        ]

    async_mock.set_stream_messages = set_stream_messages
    return async_mock


@pytest.fixture(scope="function")
def mock_setup_api_key(mocker):
    mocker.patch("mentat.session.setup_api_key")
    mocker.patch("mentat.conversation.is_model_available")
    return


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


# ContextVars need to be set in a synchronous fixture due to pytest not propagating
# async fixture contexts to test contexts.
# https://github.com/pytest-dev/pytest-asyncio/issues/127


# SessionStream
@pytest.fixture
def _mock_stream():
    session_stream = SessionStream()
    token = SESSION_STREAM.set(session_stream)
    yield session_stream
    SESSION_STREAM.reset(token)


@pytest_asyncio.fixture()
async def mock_stream(_mock_stream):
    await _mock_stream.start()
    yield _mock_stream
    await _mock_stream.stop()


# Git root
@pytest.fixture
def _mock_git_root(temp_testbed):
    git_root = Path(temp_testbed)
    token = GIT_ROOT.set(git_root)
    yield git_root
    GIT_ROOT.reset(token)


@pytest_asyncio.fixture()
async def mock_git_root(_mock_git_root):
    yield _mock_git_root


# ConfigManager
@pytest.fixture
def _mock_config():
    config = ConfigManager({}, {})
    token = CONFIG_MANAGER.set(config)
    yield config
    CONFIG_MANAGER.reset(token)


@pytest_asyncio.fixture()
async def mock_config(_mock_config):
    yield _mock_config


# CodeContext
@pytest.fixture
def _mock_code_context(_mock_git_root, _mock_config):
    code_context = CodeContext(settings=CodeContextSettings())
    token = CODE_CONTEXT.set(code_context)
    yield code_context
    CODE_CONTEXT.reset(token)


@pytest_asyncio.fixture()
async def mock_code_context(_mock_code_context):
    yield _mock_code_context


# CodeFileManager
@pytest.fixture
def _mock_code_file_manager():
    code_file_manager = CodeFileManager()
    token = CODE_FILE_MANAGER.set(code_file_manager)
    yield code_file_manager
    CODE_FILE_MANAGER.reset(token)


@pytest_asyncio.fixture()
async def mock_code_file_manager(_mock_code_file_manager):
    yield _mock_code_file_manager


# Parser
@pytest.fixture
def _mock_parser():
    parser = BlockParser()
    token = PARSER.set(parser)
    yield parser
    PARSER.reset(token)


@pytest_asyncio.fixture()
async def mock_parser(_mock_parser):
    yield _mock_parser


### Auto-used fixtures


def run_git_command(cwd, *args):
    """Helper function to run a git command."""
    subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture(autouse=True)
def temp_testbed(monkeypatch):
    # create temporary copy of testbed, complete with git repo
    # realpath() resolves symlinks, required for paths to match on macOS
    temp_dir = os.path.realpath(tempfile.mkdtemp())
    temp_testbed = os.path.join(temp_dir, "testbed")
    shutil.copytree("testbed", temp_testbed)
    shutil.copy(".gitignore", temp_testbed)

    # Initialize git repo
    run_git_command(temp_testbed, "init")

    # Set local config for user.name and user.email. Set automatically on
    # MacOS, but not Windows/Ubuntu, which prevents commits from taking.
    run_git_command(temp_testbed, "config", "user.email", "test@example.com")
    run_git_command(temp_testbed, "config", "user.name", "Test User")

    # Add all files and commit
    run_git_command(temp_testbed, "add", ".")
    run_git_command(temp_testbed, "commit", "-m", "add testbed")

    # necessary to undo chdir before calling rmtree, or it fails on windows
    with monkeypatch.context() as m:
        m.chdir(temp_testbed)
        yield temp_testbed

    shutil.rmtree(temp_dir, onerror=add_permissions)


# Always set the user config to just be a config in the temp_testbed; that way,
# it will be unset unless a specific test wants to make a config in the testbed
@pytest.fixture(autouse=True)
def mock_user_config(mocker):
    config_manager.user_config_path = Path(config_file_name)


@pytest.fixture(autouse=True)
def mock_sleep_time(mocker):
    mocker.patch.object(StreamingPrinter, "sleep_time", new=lambda self: 0)


@pytest.fixture(autouse=True)
def mock_get_codemaps(mocker):
    mocker.patch("mentat.code_map.get_code_map", return_value=[])
