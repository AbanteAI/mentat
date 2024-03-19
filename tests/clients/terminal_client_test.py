from __future__ import annotations

import subprocess
from textwrap import dedent
from typing import List

from textual.pilot import Pilot

from mentat.terminal.client import TerminalClient


def pilot(values: List[str]):
    async def auto_pilot(pilot: Pilot):
        for value in values:
            await pilot.press(*value)
            await pilot.press("enter")

    return auto_pilot


def test_empty_prompt(
    temp_testbed,
    mocker,
):
    terminal_client = TerminalClient(cwd=temp_testbed, paths=["."], headless=True, auto_pilot=pilot(["", "q"]))
    terminal_client.run()


def test_editing_file(
    temp_testbed,
    mock_call_llm_api,
):
    file_name = "test.py"
    with open(file_name, "w") as f:
        f.write("# Line 1")

    mock_call_llm_api.set_streamed_values(
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

    terminal_client = TerminalClient(
        cwd=temp_testbed,
        paths=["."],
        headless=True,
        auto_pilot=pilot(
            [
                "Edit the file",
                "y",
                "q",
            ]
        ),
    )
    terminal_client.run()
    with open(file_name, "r") as f:
        content = f.read()
        expected_content = "# Line 1\n# Line 2"
    assert content == expected_content


def test_request_and_command(
    temp_testbed,
    mock_call_llm_api,
):
    file_name = "test.py"
    mock_call_llm_api.set_streamed_values(
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

    terminal_client = TerminalClient(
        cwd=temp_testbed,
        paths=["."],
        headless=True,
        auto_pilot=pilot(
            [
                f"Create a file called {file_name}",
                "y",
                "/commit",
                "q",
            ]
        ),
    )
    terminal_client.run()

    with open(file_name, "r") as f:
        content = f.read()
    assert content == "# I created this file"
    assert subprocess.check_output(["git", "diff", "--name-only"], text=True) == ""
