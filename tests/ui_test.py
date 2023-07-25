import sys

import pytest

from mentat.app import run
from mentat.user_input_manager import UserInputManager

# These ui-tests won't run automatically
# To run them, use pytest -s --uitest
# Without the -s, pytest will capture all
# i/o and the tests will not work
pytestmark = pytest.mark.uitest


def is_test_correct():
    ans = input("Does this look correct? (Y/n)").lower()
    sys.exit(0 if ans in ["", "y"] else 1)


@pytest.fixture
def ui_mock_collect_user_input(mocker):
    mock_method = mocker.MagicMock(side_effect=is_test_correct)
    mocker.patch.object(UserInputManager, "collect_user_input", new=mock_method)
    return mock_method


def test_start(mock_call_llm_api, ui_mock_collect_user_input):
    print()
    with pytest.raises(SystemExit) as e_info:
        run(["./"])
    assert e_info.value.code == 0
