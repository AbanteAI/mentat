import re
from pathlib import Path
from textwrap import dedent

from git import Repo
import pytest
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.parsers.block_parser import BlockParser
from mentat.parsers.git_parser import GitParser
from mentat.sampler.sample import Sample
from mentat.sampler.sampler import get_active_snapshot_commit, Sampler
from mentat.session import Session
from scripts.evaluate_samples import evaluate_sample


@pytest.mark.asyncio
async def test_sample_from_context(
    mocker,
    temp_testbed,
    mock_session_context,
    mock_collect_user_input,
):
    mock_session_context.config.sample_repo = "test_sample_repo"

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
            "",
            "test_title",
            "test_description",
            "test_test_command",
        ]
    )
    sampler = Sampler()
    sample = await sampler.add_sample()
    assert sample.title == "test_title"
    assert sample.description == "test_description"
    assert sample.repo == "test_sample_repo"
    assert is_sha1(sample.merge_base)
    assert sample.diff_merge_base == ""
    assert sample.diff_active == ""
    assert sample.messages == [
        {"role": "user", "content": "test_user_content"},
        {"role": "assistant", "content": "test_assistant_content"},
    ]
    assert sample.args == ["multifile_calculator/operations.py"]
    assert (
        sample.diff_edit
        == "diff --git a/test_file.py b/test_file.py\nnew file mode 100644\nindex"
        " 0000000..ffffff\n--- /dev/null\n+++ b/test_file.py\n@@ -0,0 +1"
        " @@\n+test_file_content\n"
    )
    assert sample.id != ""
    assert sample.test_command == "test_test_command"
    assert sample.version == "0.1.0"


def is_sha1(string: str) -> bool:
    return len(string) == 40 and all(c in "0123456789abcdef" for c in string)


@pytest.mark.asyncio
async def test_sample_command(temp_testbed, mock_collect_user_input, mock_call_llm_api):
    mock_collect_user_input.set_stream_messages(
        [
            "Request",
            "y",
            f"/sample {temp_testbed}",
            "",
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
    assert sample.test_command == "test_test_command"
    assert sample.version == "0.1.0"


test_sample = {
    "title": "Add sha1",
    "description": "",
    "id": "bc62d3903f4e4945a309ea0115d16702",
    "parent_id": "",
    "repo": "http://github.com/AbanteAI/mentat",
    "merge_base": "f5057f1658b9c7edb5e45a2fa8c2198ded5b5c00",
    "diff_merge_base": "",
    "diff_active": "",
    "messages": [
        {"role": "user", "content": "Add a sha1 function to utils.py"},
        {
            "role": "assistant",
            "content": (
                "I will add a new sha1 function to the `utils.py` file.\n\nSteps:\n1."
                " Add the sha1 function to `utils.py`.\n\n"
            ),
        },
    ],
    "args": ["mentat/utils.py"],
    "diff_edit": (
        "diff --git a/mentat/utils.py b/mentat/utils.py\nindex 46c3d7f..948b7f9"
        " 100644\n--- a/mentat/utils.py\n+++ b/mentat/utils.py\n@@ -35,2 +35,6 @@ def"
        " sha256(data: str) -> str:\n \n+def sha1(data: str) -> str:\n+    return"
        ' hashlib.sha1(data.encode("utf-8")).hexdigest()\n+\n+\n async def'
        " run_subprocess_async(*args: str) -> str:\n"
    ),
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
    result = await evaluate_sample(sample)
    assert remove_checksums(result) == remove_checksums(sample.diff_edit)


def test_get_active_snapshot_commit(temp_testbed):
    repo = Repo(temp_testbed)
    # Add a test file and do an initial commit
    (temp_testbed / "test_file.py").write_text("test")
    repo.git.add("test_file.py")
    repo.git.commit("-m", "test commit")
    assert get_active_snapshot_commit(repo) == None  # No changes

    # Insert, Remove and Replace Lines
    with open(temp_testbed / "scripts" / "calculator.py", "r") as f:
        lines = f.readlines()
    lines = ["# Inserted Line\n"] + lines
    lines[20] = lines[20][:-2] + "# Replaced Line\n"
    lines = lines[:-4]  # "if __name__ == "__main__"
    with open(temp_testbed / "scripts" / "calculator.py", "w") as f:
        f.writelines(lines)

    # Create, Delete and Rename Files
    (temp_testbed / "scripts" / "calculator2.py").write_text("test")
    (temp_testbed / "scripts" / "echo.py").unlink()
    (temp_testbed / "scripts" / "graph_class.py").rename(
        temp_testbed / "scripts" / "graph.py"
    )

    commit_active = get_active_snapshot_commit(repo)

    # Confirm all changes in diff
    diff = repo.git.diff("HEAD", commit_active)
    assert "# Inserted Line" in diff
    assert "# Replaced Line" in diff
    assert "__main__" in diff
    assert "calculator2.py" in diff
    assert "echo.py" in diff
    assert "graph.py" in diff

    # Confirm current working files are unchanged
    new_lines = open(temp_testbed / "scripts" / "calculator.py", "r").readlines()
    for _line, _new_line in zip(lines, new_lines):
        assert _line == _new_line
    assert (temp_testbed / "scripts" / "calculator2.py").exists()
    assert not (temp_testbed / "scripts" / "echo.py").exists()
    assert (temp_testbed / "scripts" / "graph.py").exists()
    assert not (temp_testbed / "scripts" / "graph_class.py").exists()
