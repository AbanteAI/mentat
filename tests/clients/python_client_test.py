from pathlib import Path
from textwrap import dedent

import pytest

from mentat.python_client.client import PythonClient


@pytest.mark.asyncio
async def test_editing_file_auto_accept(
    mock_call_llm_api,
):
    file_name = "test.py"
    with open(file_name, "w") as f:
        f.write("# Line 1")

    mock_call_llm_api.set_streamed_values([dedent(f"""\
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
        @@end""")])
    python_client = PythonClient(cwd=Path.cwd(), paths=["."])
    await python_client.startup()
    await python_client.call_mentat_auto_accept("Conversation")
    await python_client.wait_for_edit_completion()
    with open(file_name, "r") as f:
        content = f.read()
        expected_content = "# Line 1\n# Line 2"
    assert content == expected_content
    await python_client.shutdown()


@pytest.mark.asyncio
async def test_collects_mentat_response(
    mock_call_llm_api,
):
    file_name = "test.py"
    with open(file_name, "w") as f:
        f.write("# Line 1")

    mock_call_llm_api.set_streamed_values([dedent(f"""\
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
        @@end""")])

    python_client = PythonClient(cwd=Path.cwd(), paths=["."])
    await python_client.startup()
    response = await python_client.call_mentat("Conversation")
    response += await python_client.call_mentat("y")
    assert "Conversation" in response
    assert "Apply these changes? 'Y/n/i' or provide feedback." in response
    await python_client.shutdown()
