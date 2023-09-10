import os
import subprocess

from mentat.diff_context import DiffContext, get_diff_context
from mentat.git_handler import get_commit_metadata


def _modify_git_file(temp_testbed):
    file_path = os.path.join(temp_testbed, "multifile_calculator", "operations.py")
    with open(file_path, "r") as f:
        lines = f.readlines()
    lines[-2:] = [
        "def new_function():\n",
        "    pass\n",
    ]
    with open(file_path, "w") as f:
        f.writelines(lines)
    return file_path, lines


def test_default_diff_context(mock_config, temp_testbed):
    # DiffContext.__init__() (default): active code vs last commit
    diff_context = DiffContext(mock_config)
    assert diff_context.config
    assert diff_context.target == "HEAD"
    assert diff_context.name == "HEAD (last commit)"
    assert diff_context.files == []

    # DiffContext.files (property): return git-tracked files with active changes
    assert diff_context.files == []
    file_path, modified_file = _modify_git_file(temp_testbed)
    assert diff_context.files == ["multifile_calculator/operations.py"]

    # DiffContext.annotate_file_message(): modify file_message with diff
    file_message = [
        "/multifile_calculator/operations.py",
        *[f"{i}:{line[:-2]}" for i, line in enumerate(modified_file, start=1)],
    ]
    annotated_message = diff_context.annotate_file_message(file_path, file_message)
    expected = file_message[:-2] + [
        "13:-def divide_numbers(a, b):",
        "14:-    return a / b",
        "13:+def new_function():",
        "14:+    pass",
    ]
    assert annotated_message == expected


def test_history_diff_context(mock_config, temp_testbed):
    # Modify a file, commit it, get diff against HEAD~1 (initial commit)
    file_path, modified_file = _modify_git_file(temp_testbed)
    subprocess.run(["git", "add", file_path], cwd=temp_testbed)
    subprocess.run(["git", "commit", "-m", "modified operations.py"], cwd=temp_testbed)
    diff_context = get_diff_context(mock_config, history=1)
    assert diff_context.config
    assert diff_context.target == "HEAD~1"
    assert diff_context.name == "HEAD~1: add testbed"
    assert diff_context.files == ["multifile_calculator/operations.py"]


def test_commit_diff_context(mock_config, temp_testbed):
    # Modify a file, commit it, get diff against first commit by hexsha
    file_path, modified_file = _modify_git_file(temp_testbed)
    subprocess.run(["git", "add", file_path], cwd=temp_testbed)
    subprocess.run(["git", "commit", "-m", "modified operations.py"], cwd=temp_testbed)
    last_commit = get_commit_metadata(mock_config.git_root, "HEAD~1")["hexsha"][:8]
    diff_context = get_diff_context(mock_config, commit=last_commit)
    assert diff_context.config
    assert diff_context.target == last_commit
    assert diff_context.name == f"{last_commit[:8]}: add testbed"
    assert diff_context.files == ["multifile_calculator/operations.py"]


def test_branch_diff_context(mock_config, temp_testbed):
    # Create and switch to a new branch, make changes and to master
    subprocess.run(["git", "checkout", "-b", "test_branch"], cwd=temp_testbed)
    file_path, modified_file = _modify_git_file(temp_testbed)
    diff_context = get_diff_context(mock_config, branch="master")
    assert diff_context.config
    assert diff_context.target == "master"
    assert diff_context.name == "Branch: master"
    assert diff_context.files == ["multifile_calculator/operations.py"]
