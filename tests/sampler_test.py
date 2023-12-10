import re
from pathlib import Path
from textwrap import dedent

import pytest
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.parsers.block_parser import BlockParser
from mentat.parsers.git_parser import GitParser
from mentat.sampler.sample import Sample
from mentat.session import Session


@pytest.mark.asyncio
async def test_sample_from_context(
    mocker,
    temp_testbed,
    mock_session_context,
    mock_collect_user_input,
):
    mock_session_context.config.sample_merge_base_target = "test_smbt"
    mock_session_context.config.sample_repo = "test_sample_repo"

    edit_history = mock_session_context.code_file_manager.history
    edit_history.merge_base = "test_merge_base"
    edit_history.diff_merge_base = "test_diff_merge_base"
    edit_history.diff_active = "test_diff_active"
    edit_history.hexsha_active = "test_hexsha_active"

    mocker.patch(
        "mentat.conversation.Conversation.get_messages",
        return_value=[
            ChatCompletionSystemMessageParam(
                content="test_system_content",
                role="system",
            ),
            ChatCompletionUserMessageParam(
                content="test_user_content",
                role="user",
            ),
            ChatCompletionAssistantMessageParam(
                content="test_assistant_content",
                role="assistant",
            ),
        ],
    )

    mock_session_context.code_context.include(
        "multifile_calculator/operations.py",
    )

    with open("test_file.py", "w") as f:
        f.write("test_file_content")

    mock_collect_user_input.set_stream_messages(
        [
            "test_title",
            "test_description",
            "test_test_command",
        ]
    )

    sample = await Sample.from_context()
    assert sample.title == "test_title"
    assert sample.description == "test_description"
    assert sample.repo == "test_sample_repo"
    assert sample.merge_base == "test_merge_base"
    assert sample.diff_merge_base == "test_diff_merge_base"
    assert sample.diff_active == "test_diff_active"
    assert sample.hexsha_active == "test_hexsha_active"
    assert sample.messages == [
        {"role": "user", "content": "test_user_content"},
        {"role": "assistant", "content": "test_assistant_content"},
    ]
    assert sample.args == ["multifile_calculator/operations.py"]
    assert (
        sample.diff_edit
        == "diff --git a/test_file.py b/test_file.py\nnew file mode 100644\nindex"
        " 0000000..ffffff\n--- /dev/null\n+++ b/test_file.py\n@@ -0,0 +1"
        " @@\n+test_file_content"
    )
    assert sample.hexsha_edit != ""
    assert sample.test_command == "test_test_command"
    assert sample.version == "0.1.0"


def is_sha1(string: str) -> bool:
    return len(string) == 40 and all(c in "0123456789abcdef" for c in string)


def is_sha256(string: str) -> bool:
    return len(string) == 64 and all(c in "0123456789abcdef" for c in string)


@pytest.mark.asyncio
async def test_sample_command(temp_testbed, mock_collect_user_input, mock_call_llm_api):
    mock_collect_user_input.set_stream_messages(
        [
            "Request",
            "y",
            f"/sample {temp_testbed}",
            "test_url",
            "test_title",
            "test_description",
            "test_test_command",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values([dedent("""\
        I will insert a comment in both files.

        @@start
        {
            "file": "multifile_calculator/calculator.py",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }
        @@code
        # forty two
        @@end
        @@start
        {
            "file": "test_file.py",
            "action": "create-file"
        }
        @@code
        # forty two
        @@end""")])

    session = Session(cwd=Path.cwd(), paths=["multifile_calculator/calculator.py"])
    session.start()
    await session.stream.recv(channel="client_exit")

    sample_files = list(temp_testbed.glob("sample_*.json"))
    assert len(sample_files) == 1
    sample = Sample.load(sample_files[0])

    assert sample.title == "test_title"
    assert sample.description == "test_description"
    assert sample.repo == "test_url"
    assert is_sha1(sample.merge_base)
    assert sample.diff_merge_base == ""
    assert sample.diff_active == ""
    assert is_sha256(sample.hexsha_active)
    assert len(sample.messages) == 2
    assert sample.messages[0] == {"role": "user", "content": "Request"}
    assert sample.messages[1]["role"] == "assistant"
    assert sample.messages[1]["content"].startswith("I will insert a comment")
    # TODO: This is hacky, find the correct way to split message/code
    assert "@@start" not in sample.messages[1]["content"]
    assert sample.args == [
        "multifile_calculator/calculator.py",
        "test_file.py",  # TODO: This shouldn't be here, but it's in included_files
    ]
    edits = [e for e in sample.diff_edit.split("diff --git") if e]
    assert len(edits) == 2
    assert "multifile_calculator/calculator.py" in edits[0]
    assert "+# forty two" in edits[0]
    assert "test_file.py" in edits[1]
    assert "+# forty two" in edits[1]
    assert is_sha256(sample.hexsha_edit)
    assert sample.test_command == "test_test_command"
    assert sample.version == "0.1.0"


test_sample = {
    "title": "Add sha1",
    "description": "",
    "repo": "http://github.com/AbanteAI/mentat",
    "merge_base": "f5057f1658b9c7edb5e45a2fa8c2198ded5b5c00",
    "diff_merge_base": "",
    "diff_active": "",
    "hexsha_active": "a4f532391b368bcd6d57de67da9bd81a16a3a8965f75995364c8870fa589f00f",
    "messages": [
        {"role": "user", "content": "Add a new helper function called sha1."},
        {
            "role": "assistant",
            "content": (
                "I will add a new helper function called `sha1` to the"
                " `mentat/utils.py` file.\n\nSteps:\n1. Add the `sha1` function to"
                " `mentat/utils.py`.\n\n"
            ),
        },
    ],
    "args": ["mentat/utils.py"],
    "diff_edit": (
        "diff --git a/mentat/utils.py b/mentat/utils.py\nindex f90a755..6d9744a"
        " 100644\n--- a/mentat/utils.py\n+++ b/mentat/utils.py\n@@ -34,0 +35,2 @@ def"
        " sha256(data: str) -> str:\n+def sha1(data: str) -> str:\n+    return"
        ' hashlib.sha1(data.encode("utf-8")).hexdigest()'
    ),
    "hexsha_edit": "b790990b55d01b7022324e87dd6f6fa9134849f1c379242c13f01508f6ce8851",
    "test_command": "",
    "version": "0.1.0",
}


@pytest.mark.asyncio
async def test_sample_eval(mock_call_llm_api):
    parsedLLMResponse = GitParser().parse_string(test_sample["diff_edit"])
    edit_message = BlockParser().file_edits_to_llm_message(parsedLLMResponse)
    mock_call_llm_api.set_streamed_values([dedent(f"""\
        I will add a new helper function called `sha1` to the `mentat/utils.py` file.
        
        Steps:
        1. Add the `sha1` function to `mentat/utils.py`.{edit_message}""")])

    def remove_checksums(text):
        pattern = r"\b[0-9a-f]{7}\b"
        return re.sub(pattern, "", text)

    sample = Sample(**test_sample)
    result = await sample.eval()
    assert remove_checksums(result["diff_eval"]) == remove_checksums(sample.diff_edit)
    assert result["hexsha_eval"] == sample.hexsha_edit
