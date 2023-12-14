import os
import subprocess

from mentat.git_handler import get_diff_active, get_diff_commit, get_hexsha_active


def test_get_diff_commit(temp_testbed, mock_session_context):
    # Add a new file and commit it, then delete but don't commit
    with open("test_file.txt", "w") as f:
        f.write("forty two")
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "test commit"])
    os.remove("test_file.txt")

    # Expect the diff to contain the new file
    diff = get_diff_commit("HEAD~1")
    assert "forty two" in diff


def test_get_diff_active(temp_testbed):
    # New file
    with open("test_file.txt", "w") as f:
        f.write("forty two")
    diff = get_diff_active()
    assert "forty two" in diff

    # Changes to a file
    with open("multifile_calculator/calculator.py", "a") as f:
        f.write("forty three")
    diff = get_diff_active()
    assert "forty three" in diff


def test_get_hexsha_active(temp_testbed):
    a = get_hexsha_active()
    with open("multifile_calculator/calculator.py", "a") as f:
        f.write("forty three")
    b = get_hexsha_active()
    with open("test_file.txt", "w") as f:
        f.write("forty two")
    c = get_hexsha_active()
    assert a != b
    assert b != c
    assert a != c
