import os
import subprocess
from textwrap import dedent

import pytest
from prompt_toolkit import PromptSession

from mentat.app import run

# Unfortunately these tests just can't be run on Windows
pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="PromptSession throws an error on Github Actions Windows runner",
)


@pytest.fixture
def mock_prompt_session_prompt(mocker):
    mock_method = mocker.MagicMock()
    # Mock the super().prompt that MentatPromptSession calls
    mocker.patch.object(PromptSession, "prompt", new=mock_method)
    return mock_method


def test_request_and_command(
    mock_prompt_session_prompt, mock_call_llm_api, mock_setup_api_key
):
    file_name = "hello_world.py"
    mock_prompt_session_prompt.side_effect = [
        f"Create a file called {file_name}",
        "y",
        "/commit",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent(f"""\
        I will create a new file called temp.py

        Steps: 1. Create a new file called temp.py

        @@start
        {{
            "file": "{file_name}",
            "action": "create-file"
        }}
        @@code
        # I created this file
        @@end""")])

    run(["."])

    with open(file_name, "r") as f:
        content = f.read()
    assert content == "# I created this file"
    assert subprocess.check_output(["git", "diff", "--name-only"], text=True) == ""
