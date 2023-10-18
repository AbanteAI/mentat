from textwrap import dedent

import pytest

from mentat.python_client.client import PythonClient


@pytest.mark.asyncio
async def test_editing_file_auto_accept(mock_call_llm_api, mock_setup_api_key):
    file_name = "test.py"
    with open(file_name, "w") as f:
        f.write("# Line 1")

    mock_call_llm_api.set_generator_values([dedent(f"""\
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

    python_client = PythonClient(["."])
    await python_client.call_mentat_auto_accept("Conversation")
    with open(file_name, "r") as f:
        content = f.read()
        expected_content = "# Line 1\n# Line 2"
    assert content == expected_content
    await python_client.stop()


@pytest.mark.asyncio
async def test_collects_mentat_response(mock_call_llm_api, mock_setup_api_key):
    file_name = "test.py"
    with open(file_name, "w") as f:
        f.write("# Line 1")

    mock_call_llm_api.set_generator_values([dedent(f"""\
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

    python_client = PythonClient(["."])
    response = await python_client.call_mentat("Conversation")
    assert "Conversation" in response
    assert "Apply these changes? 'Y/n/i' or provide feedback." in response
    await python_client.stop()
