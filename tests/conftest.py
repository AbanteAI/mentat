import os
import shutil
import stat
import subprocess
import tempfile

import pytest

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
    mocker.patch("mentat.conversation.check_model_availability")
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


# Auto-used fixtures


@pytest.fixture(autouse=True)
def temp_testbed(monkeypatch):
    # create temporary copy of testbed, complete with git repo
    # realpath() resolves symlinks, required for paths to match on macOS
    temp_dir = os.path.realpath(tempfile.mkdtemp())
    temp_testbed = os.path.join(temp_dir, "testbed")
    shutil.copytree("testbed", temp_testbed)
    shutil.copy(".gitignore", temp_testbed)
    subprocess.run(
        ["git", "init"],
        cwd=temp_testbed,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=temp_testbed,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "commit", "-m", "add testbed"],
        cwd=temp_testbed,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # necessary to undo chdir before calling rmtree, or it fails on windows
    with monkeypatch.context() as m:
        m.chdir(temp_testbed)
        yield temp_testbed

    shutil.rmtree(temp_dir, onerror=add_permissions)


@pytest.fixture(autouse=True)
def mock_sleep_time(mocker):
    mocker.patch.object(StreamingPrinter, "sleep_time", new=lambda self: 0)


# Creating a prompt session in Github Actions on Windows throws an error
# even though we don't use it, so we always have to mock the prompt session.
@pytest.fixture(autouse=True)
def mock_prompt_session(mocker):
    mocker.patch("mentat.user_input_manager.PromptSession")
