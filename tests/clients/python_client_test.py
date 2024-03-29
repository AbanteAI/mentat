from textwrap import dedent
from unittest.mock import MagicMock

import pytest

from mentat.python_client.client import PythonClient


@pytest.mark.asyncio
async def test_editing_file_auto_accept(temp_testbed, mock_call_llm_api):
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

    python_client = PythonClient(cwd=temp_testbed, paths=["."])
    await python_client.startup()
    await python_client.call_mentat_auto_accept("Conversation")
    with open(file_name, "r") as f:
        content = f.read()
        expected_content = "# Line 1\n# Line 2"
    assert content == expected_content
    await python_client.shutdown()


@pytest.mark.asyncio
async def test_collects_mentat_response(temp_testbed, mock_call_llm_api):
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

    python_client = PythonClient(cwd=temp_testbed, paths=["."])
    await python_client.startup()
    response = await python_client.call_mentat("Conversation")
    response += await python_client.call_mentat("y")
    assert "Conversation" in response
    assert "Apply these changes? 'Y/n/i' or provide feedback." in response
    await python_client.shutdown()


@pytest.mark.asyncio
async def test_graceful_failure_on_session_exit(temp_testbed):
    python_client = PythonClient()
    await python_client.startup()

    python_client.session.ctx.llm_api_handler.initialize_client = MagicMock(side_effect=Exception("test"))
    with pytest.raises(Exception, match="Session failed"):
        await python_client.call_mentat("Conversation")
