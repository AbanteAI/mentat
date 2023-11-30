from unittest.mock import MagicMock

import pytest

from mentat.code_map import check_ctags_disabled, get_code_map, get_ctags


@pytest.mark.no_git_testbed
def test_get_ctags(temp_testbed, mock_call_llm_api):
    echo_py_abs_file_path = temp_testbed.joinpath("scripts/echo.py")

    ctags_with_signatures = get_ctags(echo_py_abs_file_path)
    assert ctags_with_signatures == {
        (None, "function", "echo", "(value: Any)", 4),
        (None, "function", "echo_hardcoded", "()", 8),
    }

    ctags_without_signatures = get_ctags(echo_py_abs_file_path, exclude_signatures=True)
    assert ctags_without_signatures == {
        (None, "function", "echo", None, 4),
        (None, "function", "echo_hardcoded", None, 8),
    }


@pytest.mark.no_git_testbed
def test_check_ctags_disabled(mocker, temp_testbed):
    assert check_ctags_disabled() is None

    # mock subprocess.check_output
    mock = mocker.patch(
        "mentat.code_map.subprocess.check_output",
        new_callable=MagicMock,
    )
    check_ctags_disabled()
    assert not mock.called
