import subprocess
from pathlib import Path

import pytest

from mentat.diff_context import DiffContext
from mentat.python_client.client import PythonClient
from mentat.session_context import SESSION_CONTEXT


def _update_ops(temp_testbed, last_line, commit_message=None):
    # Update the last line of operations.py and (optionally) commit
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    with open(abs_path, "r") as f:
        lines = f.readlines()
    lines[-1:] = [
        f"    return {last_line}\n",
    ]
    with open(abs_path, "w") as f:
        f.writelines(lines)
    if commit_message:
        subprocess.run(["git", "add", abs_path], cwd=temp_testbed)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=temp_testbed)


@pytest.fixture
def git_history(temp_testbed, mock_session_context):
    """Load a git repo with the following branches/commits:

    main
      'a / b' (from temp_testbed)
      'commit2'
      'commit3'
    test_branch (from commit2)
      'commit4'
    """
    _update_ops(temp_testbed, "commit2", "commit2")
    _update_ops(temp_testbed, "commit3", "commit3")
    subprocess.run(["git", "checkout", "HEAD~1"], cwd=temp_testbed)
    subprocess.run(["git", "checkout", "-b", "test_branch"], cwd=temp_testbed)
    # commit4
    _update_ops(temp_testbed, "commit4", "commit4")
    # Return on master commit3
    subprocess.run(["git", "checkout", "master"], cwd=temp_testbed)


def _get_file_message(abs_path):
    file_message = ["/multifile_calculator/operations.py"]
    with open(abs_path, "r") as f:
        for i, line in enumerate(f.readlines()):
            file_message.append(f"{i}:{line}")
    return file_message


def test_diff_context_default(temp_testbed, git_history, mock_session_context):
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    # DiffContext.__init__() (default): active code vs last commit
    diff_context = DiffContext(
        mock_session_context.stream, mock_session_context.git_root
    )
    assert diff_context.target == "HEAD"
    assert diff_context.name == "HEAD (last commit)"
    assert diff_context.files == []

    # DiffContext.files (property): return git-tracked files with active changes
    _update_ops(temp_testbed, "commit5")
    diff_context._files_cache = None  # This is usually cached
    assert diff_context.files == [abs_path]

    # DiffContext.annotate_file_message(): modify file_message with diff
    file_message = _get_file_message(abs_path)
    annotated_message = diff_context.annotate_file_message(abs_path, file_message)
    expected = file_message[:-1] + [
        "14:-    return commit3",
        "14:+    return commit5",
    ]
    assert annotated_message == expected


@pytest.mark.asyncio
async def test_diff_context_commit(temp_testbed, git_history, mock_session_context):
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    # Get the hash of 2-commits-ago
    last_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD~2"], cwd=temp_testbed, text=True
    ).strip()
    diff_context = DiffContext(
        mock_session_context.stream, mock_session_context.git_root, diff=last_commit
    )
    assert diff_context.target == last_commit
    assert diff_context.name == f"{last_commit[:8]}: add testbed"
    assert diff_context.files == [abs_path]

    file_message = _get_file_message(abs_path)
    annotated_message = diff_context.annotate_file_message(abs_path, file_message)
    expected = file_message[:-1] + [
        "14:-    return a / b",
        "14:+    return commit3",
    ]
    assert annotated_message == expected


@pytest.mark.asyncio
async def test_diff_context_branch(temp_testbed, git_history, mock_session_context):
    diff_context = DiffContext(
        mock_session_context.stream, mock_session_context.git_root, diff="test_branch"
    )
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    assert diff_context.target == "test_branch"
    assert diff_context.name.startswith("Branch test_branch:")
    assert diff_context.name.endswith(": commit4")
    assert diff_context.files == [abs_path]

    file_message = _get_file_message(abs_path)
    annotated_message = diff_context.annotate_file_message(abs_path, file_message)
    expected = file_message[:-1] + [
        "14:-    return commit4",
        "14:+    return commit3",
    ]
    assert annotated_message == expected


@pytest.mark.asyncio
async def test_diff_context_relative(temp_testbed, git_history, mock_session_context):
    diff_context = DiffContext(
        mock_session_context.stream, mock_session_context.git_root, diff="HEAD~2"
    )
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    assert diff_context.target == "HEAD~2"
    assert diff_context.name.startswith("HEAD~2: ")
    assert diff_context.name.endswith(": add testbed")
    assert diff_context.files == [abs_path]

    file_message = _get_file_message(abs_path)
    annotated_message = diff_context.annotate_file_message(abs_path, file_message)
    expected = file_message[:-1] + [
        "14:-    return a / b",
        "14:+    return commit3",
    ]
    assert annotated_message == expected


@pytest.mark.asyncio
async def test_diff_context_pr(temp_testbed, git_history, mock_session_context):
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    subprocess.run(["git", "checkout", "test_branch"], cwd=temp_testbed)
    diff_context = DiffContext(
        mock_session_context.stream, mock_session_context.git_root, pr_diff="master"
    )

    commit2 = subprocess.check_output(
        ["git", "rev-parse", "HEAD~1"], cwd=temp_testbed, text=True
    ).strip()
    assert diff_context.target == commit2
    assert diff_context.name.startswith("Merge-base Branch master:")
    assert diff_context.name.endswith(": commit2")  # NOT the latest
    assert diff_context.files == [abs_path]


@pytest.mark.asyncio
async def test_diff_context_end_to_end(
    temp_testbed, git_history, mock_call_llm_api, mock_setup_api_key
):
    abs_path = Path(temp_testbed) / "multifile_calculator" / "operations.py"

    # SESSION_CONTEXT isn't reset between tests
    SESSION_CONTEXT.set(None)
    mock_call_llm_api.set_generator_values([""])
    python_client = PythonClient([], diff="HEAD~2")
    await python_client.startup()

    session_context = SESSION_CONTEXT.get()
    code_context = session_context.code_context
    code_message = await code_context.get_code_message("test", 1)
    diff_context = code_context.diff_context

    assert diff_context.target == "HEAD~2"
    assert diff_context.name.startswith("HEAD~2: ")
    assert diff_context.name.endswith(": add testbed")
    assert diff_context.files == [abs_path]

    assert "multifile_calculator" in code_message

    await python_client.call_mentat("Conversation")
    await python_client.shutdown()
