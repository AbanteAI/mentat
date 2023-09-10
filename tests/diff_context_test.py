import os
import subprocess

from mentat.diff_context import DiffContext
from mentat.git_handler import get_commit_metadata

def _run_subprocess(command, cwd):
    return subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

# TODO: Split into separate tests

# Make sure it initialized properly with a commit, branch, History or None
def test_diff_context(mock_config, temp_testbed):
    # When initialized empty, it should have no files
    diff_context = DiffContext(mock_config)
    assert diff_context.files == []

    # Add a file and commit it
    file_path = os.path.join(temp_testbed, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("I am a file\n")
    _run_subprocess(["git", "add", "."], temp_testbed)
    _run_subprocess(["git", "commit", "-m", "add test_file"], temp_testbed)

    # Test history / create file
    diff_context = DiffContext(mock_config, history=1)
    assert diff_context.files == ["test_file.txt"]
    _hash = diff_context.target[:8]
    assert diff_context.name == f"HEAD~1: add testbed"
    file_message = ["/test_file.txt", "1:I am a file"]
    annotated_message = diff_context.annotate_file_message(
        "test_file.txt", file_message
    )
    assert annotated_message == ["/test_file.txt", "1:+I am a file"]

    # Update a file and commit it
    with open(file_path, "w") as file:
        file.write("I am a file\nI am updated\n")
    _run_subprocess(["git", "add", "."], temp_testbed)
    _run_subprocess(["git", "commit", "-m", "update test_file"], temp_testbed)

    # Test commit / update file
    last_commit = get_commit_metadata(mock_config.git_root, "HEAD~1")['hexsha']
    diff_context = DiffContext(mock_config, commit=last_commit)
    assert diff_context.files == ["test_file.txt"]
    _hash = diff_context.target[:8]
    assert diff_context.name == f"{_hash}: add test_file"
    file_message = ["/test_file.txt", "1:I am a file", "2:I am updated"]
    annotated_message = diff_context.annotate_file_message(
        "test_file.txt", file_message
    )
    assert annotated_message == ["/test_file.txt", "1:I am a file", "2:+I am updated"]

    # Text branch / remove lines
    _run_subprocess(["git", "checkout", "-b", "test_branch"], temp_testbed)
    with open(file_path, "w") as file:
        file.write("I am updated\n")

    # Test branch / remove lines
    diff_context = DiffContext(mock_config, branch="master")
    assert diff_context.files == ["test_file.txt"]
    assert diff_context.name == "Branch: master"
    file_message = ["/test_file.txt", "1:I am updated"]
    annotated_message = diff_context.annotate_file_message(
        "test_file.txt", file_message
    )
    assert annotated_message == ["/test_file.txt", "0:-I am a file", "1:I am updated"]
