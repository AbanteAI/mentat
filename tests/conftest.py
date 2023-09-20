import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from mentat.config_manager import ConfigManager
from mentat.streaming_printer import StreamingPrinter
from mentat.user_input_manager import UserInputManager

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


@pytest.fixture
def mock_call_llm_api(mocker):
    mock = mocker.patch("mentat.parsing.call_llm_api")

    def set_generator_values(values):
        async def async_generator():
            for value in values:
                yield {"choices": [{"delta": {"content": value}}]}

        mock.return_value = async_generator()

    mock.set_generator_values = set_generator_values
    return mock


@pytest.fixture
def mock_collect_user_input(mocker):
    mock_method = mocker.MagicMock()
    mocker.patch.object(UserInputManager, "collect_user_input", new=mock_method)

    return mock_method


@pytest.fixture
def mock_setup_api_key(mocker):
    mocker.patch("mentat.app.setup_api_key")
    mocker.patch("mentat.conversation.is_model_available")
    return


@pytest.fixture
def mock_config(temp_testbed):
    config = ConfigManager(Path(temp_testbed))
    config.project_config = {}
    return config


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


# Auto-used fixtures
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


@pytest.fixture(autouse=True)
def mock_sleep_time(mocker):
    mocker.patch.object(StreamingPrinter, "sleep_time", new=lambda self: 0)


# Creating a prompt session in Github Actions on Windows throws an error
# even though we don't use it, so we always have to mock the prompt session on Windows
@pytest.fixture(autouse=True)
def mock_prompt_session(mocker):
    # Only mock these on Windows
    if os.name == "nt":
        mocker.patch("mentat.user_input_manager.PromptSession")
        mocker.patch("mentat.user_input_manager.MentatPromptSession")
