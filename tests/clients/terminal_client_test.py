import os
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock

import pytest
from prompt_toolkit import PromptSession

from mentat.terminal.client import TerminalClient

# Unfortunately these tests just can't be run on Windows
pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="PromptSession throws an error on Github Actions Windows runner",
)


@pytest.fixture
def mock_prompt_session_prompt(mocker):
    mock_method = AsyncMock()
    mocker.patch.object(PromptSession, "prompt_async", new=mock_method)
    return mock_method


def test_editing_file(
    mock_prompt_session_prompt, mock_call_llm_api, mock_setup_api_key
):
    file_name = "test.py"
    with open(file_name, "w") as f:
        f.write("# Line 1")
    mock_prompt_session_prompt.side_effect = [
        "",
        "y",
        "q",
    ]

    mock_call_llm_api.set_generator_values(
        [
            dedent(
                f"""\
        Conversation

        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-before-line": 2,
            "insert-after-line": 1
        }}
        @@code
        # Line 2
        @@end"""
            )
        ]
    )

    terminal_client = TerminalClient(cwd=Path("."), paths=[Path(".")])
    terminal_client.run()
    with open(file_name, "r") as f:
        content = f.read()
        expected_content = "# Line 1\n# Line 2"
    assert content == expected_content


def test_request_and_command(
    mock_prompt_session_prompt, mock_call_llm_api, mock_setup_api_key
):
    file_name = "test.py"
    mock_prompt_session_prompt.side_effect = [
        f"Create a file called {file_name}",
        "y",
        "/commit",
        "q",
    ]

    mock_call_llm_api.set_generator_values(
        [
            dedent(
                f"""\
        I will create a new file called temp.py

        Steps: 1. Create a new file called temp.py

        @@start
        {{
            "file": "{file_name}",
            "action": "create-file"
        }}
        @@code
        # I created this file
        @@end"""
            )
        ]
    )

    terminal_client = TerminalClient(cwd=Path("."), paths=[Path(".")])
    terminal_client.run()

    with open(file_name, "r") as f:
        content = f.read()
    assert content == "# I created this file"
    assert subprocess.check_output(["git", "diff", "--name-only"], text=True) == ""
