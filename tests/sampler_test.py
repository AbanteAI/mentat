import json
import re
from pathlib import Path
from textwrap import dedent

import pytest
from git import Repo
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from benchmarks.run_sample import run_sample
from mentat import Mentat
from mentat.conversation import MentatAssistantMessageParam
from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.git_parser import GitParser
from mentat.parsers.parser import ParsedLLMResponse
from mentat.sampler import __version__
from mentat.sampler.sample import Sample
from mentat.sampler.sampler import Sampler
from mentat.sampler.utils import get_active_snapshot_commit
from mentat.session import Session


def remove_checksums(text):
    pattern = r"\b[0-9a-f]{7}\b"
    return re.sub(pattern, "", text)


@pytest.mark.asyncio
async def test_sample_from_context(
    mocker,
    temp_testbed,
    mock_session_context,
    mock_collect_user_input,
):
    mock_session_context.config.sample_repo = "test_sample_repo"
    mock_session_context.config.sampler = True

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
            MentatAssistantMessageParam(
                parsed_llm_response=ParsedLLMResponse("", "test_assistant_content", []),
                content="test_assistant_content",
                role="assistant",
            ),
        ],
    )

    mock_session_context.code_context.include(
        "multifile_calculator/operations.py",
    )

    with open("test_file.py", "w") as f:
        f.write("test_file_content\n")

    mock_collect_user_input.set_stream_messages(
        [
            "",
            "test_title",
            "test_description",
            "test_test_command",
        ]
    )
    sampler = Sampler()
    sampler.set_active_diff()
    sample = await sampler.create_sample()
    assert sample.title == "test_title"
    assert sample.description == "test_description"
    assert sample.repo == "test_sample_repo"
    assert is_sha1(sample.merge_base)
    assert sample.diff_merge_base == ""
    expected_diff = (
        "diff --git a/test_file.py b/test_file.py\nnew file mode 100644\nindex"
        " 0000000..fffffff\n--- /dev/null\n+++ b/test_file.py\n@@ -0,0 +1"
        " @@\n+test_file_content\n"
    )
    assert remove_checksums(sample.diff_active) == remove_checksums(expected_diff)
    assert sample.message_history == []
    assert sample.message_prompt == "test_user_content"
    assert sample.message_edit == "test_assistant_content"
    assert sample.context == ["multifile_calculator/operations.py"]
    assert sample.diff_edit == ""
    assert sample.id != ""
    assert sample.FAIL_TO_PASS == json.dumps(["test_test_command"])
    assert sample.version == __version__


def is_sha1(string: str) -> bool:
    return len(string) == 40 and all(c in "0123456789abcdef" for c in string)


@pytest.mark.asyncio
async def test_sample_command(temp_testbed, mock_collect_user_input, mock_call_llm_api):
    mock_collect_user_input.set_stream_messages(
        [
            "Request",
            "y",
            f"/sample {temp_testbed.as_posix()}",
            "",
            "test_url",
            "test_title",
            "test_description",
            "test_test_command",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
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
        @@end"""
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=[Path("multifile_calculator/calculator.py")])
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
    assert sample.message_history == []
    assert sample.message_prompt == "Request"
    assert sample.message_edit == "I will insert a comment in both files."
    assert sample.context == [
        "multifile_calculator/calculator.py",
    ]
    edits = [e for e in sample.diff_edit.split("diff --git") if e]
    assert len(edits) == 2
    assert "multifile_calculator/calculator.py" in edits[0]
    assert "+# forty two" in edits[0]
    assert "test_file.py" in edits[1]
    assert "+# forty two" in edits[1]
    assert sample.FAIL_TO_PASS == json.dumps(["test_test_command"])
    assert sample.version == "0.3.0"


test_sample = {
    "title": "Add sha1",
    "description": "",
    "id": "bc62d3903f4e4945a309ea0115d16702",
    "parent_id": "",
    "repo": "http://github.com/AbanteAI/mentat",
    "merge_base": "f5057f1658b9c7edb5e45a2fa8c2198ded5b5c00",
    "diff_merge_base": "",
    "diff_active": "",
    "message_history": [],
    "message_prompt": "Add a sha1 function to utils.py",
    "message_edit": (
        "I will add a new sha1 function to the `utils.py` file.\n\nSteps:\n1. Add the sha1 function to `utils.py`."
    ),
    "context": ["mentat/utils.py"],
    "diff_edit": (
        "diff --git a/mentat/utils.py b/mentat/utils.py\nindex 46c3d7f..948b7f9"
        " 100644\n--- a/mentat/utils.py\n+++ b/mentat/utils.py\n@@ -35,2 +35,6 @@ def"
        " sha256(data: str) -> str:\n \n+def sha1(data: str) -> str:\n+    return"
        ' hashlib.sha1(data.encode("utf-8")).hexdigest()\n+\n+\n async def'
        " run_subprocess_async(*args: str) -> str:\n"
    ),
    "FAIL_TO_PASS": "",
    "version": "0.3.0",
}


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_sample_eval(temp_testbed, mock_call_llm_api):
    parsedLLMResponse = GitParser().parse_llm_response(test_sample["diff_edit"])
    edit_message = BlockParser().file_edits_to_llm_message(parsedLLMResponse)
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                f"""\
        I will add a new helper function called `sha1` to the `mentat/utils.py` file.
        
        Steps:
        1. Add the `sha1` function to `mentat/utils.py`.{edit_message}"""
            )
        ]
    )

    sample = Sample(**test_sample)
    result = await run_sample(sample)
    diff_eval = result["diff_eval"]
    assert remove_checksums(diff_eval) == remove_checksums(sample.diff_edit)


@pytest.mark.asyncio
async def test_sample_version_mismatch(temp_testbed):
    sample = Sample(**test_sample)
    sample.version = "2.3"
    sample_path = temp_testbed / "temp_sample.json"
    sample.save(sample_path)
    with pytest.raises(SampleError):
        Sample.load(sample_path)


def test_get_active_snapshot_commit(temp_testbed):
    repo = Repo(temp_testbed)
    # Add a test file and do an initial commit
    with open(temp_testbed / "test_file.py", "w") as f:
        f.write("test")
    repo.git.add("test_file.py")
    repo.git.commit("-m", "test commit")
    assert get_active_snapshot_commit(repo) is None  # No changes

    # Insert, Remove and Replace Lines
    with open(temp_testbed / "scripts" / "calculator.py", "r") as f:
        lines = f.readlines()
    lines = ["# Inserted Line\n"] + lines
    lines[20] = lines[20][:-2] + "# Replaced Line\n"
    lines = lines[:-4]  # "if __name__ == "__main__"
    with open(temp_testbed / "scripts" / "calculator.py", "w") as f:
        f.writelines(lines)

    # Create, Delete and Rename Files
    with open(temp_testbed / "scripts" / "calculator2.py", "w") as f:
        f.write("test")
    (temp_testbed / "scripts" / "echo.py").unlink()
    (temp_testbed / "scripts" / "graph_class.py").rename(temp_testbed / "scripts" / "graph.py")

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
    with open(temp_testbed / "scripts" / "calculator.py", "r") as f:
        new_lines = f.readlines()
    for _line, _new_line in zip(lines, new_lines):
        assert _line == _new_line
    assert (temp_testbed / "scripts" / "calculator2.py").exists()
    assert not (temp_testbed / "scripts" / "echo.py").exists()
    assert (temp_testbed / "scripts" / "graph.py").exists()
    assert not (temp_testbed / "scripts" / "graph_class.py").exists()


def make_all_update_types(cwd, index):
    assert index in range(3)
    # Insert, Remove and Replace Lines
    with open(cwd / "multifile_calculator" / "operations.py", "r") as f:
        text_string = f.read()
    lines = text_string.split("\n")
    # Remove empty newline at end
    if lines[-1] == "":
        lines = lines[:-1]
    lines = [f"# Inserted Line {index}"] + lines
    lines[5] += f" # Replaced Line {index}"
    # Remove the last line and any empties before it
    lines = lines[:-1]
    while lines[-1] == "":
        lines = lines[:-1]
    # Add a final empty line
    lines.append("")
    with open(cwd / "multifile_calculator" / "operations.py", "w") as f:
        f.write("\n".join(lines))

    # Create, Delete and Rename Files
    with open(cwd / "multifile_calculator" / f"calculator{index}.py", "w") as f:
        f.write("test\n")
    format_examples = ["block.txt", "git_diff.txt", "replacement.txt"]
    (cwd / "format_examples" / format_examples[index]).unlink()
    old_name = "echo.py" if index == 0 else f"echo{index-1}.py"
    (cwd / "scripts" / old_name).rename(cwd / "scripts" / f"echo{index}.py")


def get_updates_as_parsed_llm_message(cwd):
    repo = Repo(cwd)
    starting_diff = repo.git.diff()
    # Commit active changes
    commit_active = get_active_snapshot_commit(repo)
    repo.git.add("--all")
    repo.git.commit("-m", "temporary commit")
    # Make diff_edit edits
    make_all_update_types(cwd, 2)
    diff_edit = get_git_diff("HEAD", cwd)
    parsedLLMResponse = GitParser().parse_llm_response(diff_edit)
    # Reset hard and remove uncommitted files
    repo.git.reset("--hard")
    repo.git.clean("-fd")
    # Reset to previous commit, but keep changes as active
    repo.git.checkout("HEAD~1")
    # Re-apply the changes from commit_active without commiting
    repo.git.execute(["git", "cherry-pick", commit_active, "--no-commit"])
    # Unstage all changes
    repo.git.reset()
    ending_diff = repo.git.diff()
    if starting_diff != ending_diff:
        raise SampleError("Git state was not reset accurately.")

    return parsedLLMResponse


@pytest.mark.asyncio
async def test_sampler_integration(temp_testbed, mock_session_context, mock_call_llm_api):
    # Setup the environemnt
    repo = Repo(temp_testbed)
    (temp_testbed / "test_file.py").write_text("permanent commit")
    repo.git.add("test_file.py")
    merge_base = repo.head.commit.hexsha
    # Make diff_merge_base edits + commit
    make_all_update_types(temp_testbed, 0)
    repo.git.add("--all")
    repo.git.commit("-m", "temporary commit")
    # Make diff_active edits
    make_all_update_types(temp_testbed, 1)

    # Verify it's setup correctly
    with open(temp_testbed / "multifile_calculator" / "operations.py", "r") as f:
        lines = f.readlines()
    for i in range(2):
        assert any(f"# Inserted Line {i}" in line for line in lines)
        assert any(f"# Replaced Line {i}" in line for line in lines)
    assert not any("# Inserted Line 2" in line for line in lines)
    assert not any("# Replaced Line 2" in line for line in lines)
    assert lines[-1] == "    return a - b\n"
    assert (temp_testbed / "multifile_calculator" / "calculator0.py").exists()
    assert (temp_testbed / "multifile_calculator" / "calculator1.py").exists()
    assert not (temp_testbed / "format_examples" / "block.txt").exists()
    assert not (temp_testbed / "format_examples" / "git_diff.txt").exists()
    assert (temp_testbed / "format_examples" / "replacement.txt").exists()

    # Generate file_edits to be performed for test, verify they're setup correctly
    parsed_llm_message = get_updates_as_parsed_llm_message(temp_testbed)
    file_edits = parsed_llm_message.file_edits
    assert any("Inserted Line 2" in str(f.replacements) for f in file_edits)
    assert any("Replaced Line 2" in str(f.replacements) for f in file_edits)
    assert any(
        # In file-edit, the entire file is overwritten, so we verify it's missing the last line
        ("operations.py" in str(f.file_path) and "return a - b" not in str(f.replacements))
        for f in file_edits
    )
    assert any("calculator2.py" in str(f.file_path) for f in file_edits)
    assert any("replacement.txt" in str(f.file_path) for f in file_edits)

    llm_response = BlockParser().file_edits_to_llm_message(parsed_llm_message)
    mock_call_llm_api.set_streamed_values([f"I will make the following edits. {llm_response}"])

    # Generate a sample using Mentat
    client = Mentat(cwd=temp_testbed, paths=["."])
    await client.startup()
    client.session.ctx.config.sampler = True
    await client.call_mentat_auto_accept(
        dedent(
            """\
        Make the following changes to "multifile_calculator/operations.py":
        1. Add "# Inserted line 2" as the first line
        2. Add "# Replaced Line 2" to the end of the 5th line
        3. Remove the last non-blank line
        Make the following other changes:
        4. Create "multifile_calculator/calculator2.py"
        5. Delete "format_examples/replacement.txt"
        6. Rename "scripts/echo1.py" to "scripts/echo2.py"
        """
        )
    )

    # Remove all included files; rely on the diff to include them
    client.session.ctx.code_context.include_files = {}
    await client.call_mentat(f"/sample {temp_testbed.as_posix()}")
    await client.call_mentat(merge_base)
    await client.call_mentat("test_url")
    await client.call_mentat("test_title")
    await client.call_mentat("test_description")
    await client.call_mentat("")
    await client.call_mentat("q")
    await client.shutdown()

    # Evaluate the sample using Mentat
    sample_files = list(temp_testbed.glob("sample_*.json"))
    assert len(sample_files) == 1
    sample = Sample.load(sample_files[0])
    assert sample.title == "test_title"
    assert sample.description == "test_description"
    assert sample.repo == "test_url"
    assert sample.merge_base == merge_base
    assert sample.diff_merge_base != ""
    assert sample.diff_active != ""
    assert sample.message_history == []
    assert sample.message_edit == "I will make the following edits."
    assert set(sample.context) == {
        "scripts/echo1.py",
        "multifile_calculator/operations.py",
        "format_examples/replacement.txt",
    }
    assert sample.diff_edit != ""

    mock_call_llm_api.set_streamed_values([f"I will make the following edits. {llm_response}"])
    result = await run_sample(sample, temp_testbed)
    diff_eval = result["diff_eval"]
    assert diff_eval == sample.diff_edit
