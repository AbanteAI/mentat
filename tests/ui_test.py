import sys
from unittest.mock import AsyncMock

import pytest

from mentat.terminal.client import TerminalClient

# These ui-tests won't run automatically
# To run them, use pytest -s --uitest
# Without the -s, pytest will capture all
# i/o and the tests will not work
pytestmark = pytest.mark.uitest


def is_test_correct():
    ans = input("Does this look correct? (Y/n)").lower()
    sys.exit(0 if ans in ["", "y"] else 1)


@pytest.fixture
def ui_mock_collect_user_input(
    mocker,
):
    async_mock = AsyncMock()

    mocker.patch("mentat.code_edit_feedback.collect_user_input", side_effect=async_mock)
    mocker.patch("mentat.session_input.collect_user_input", side_effect=async_mock)
    mocker.patch("mentat.session.collect_user_input", side_effect=async_mock)

    async_mock.side_effect = is_test_correct
    return async_mock


def test_start(mock_call_llm_api, ui_mock_collect_user_input):
    print()
    with pytest.raises(SystemExit) as e_info:
        terminal_client = TerminalClient(["."])
        terminal_client.run()
    assert e_info.value.code == 0
