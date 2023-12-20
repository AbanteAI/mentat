import os
import subprocess

from mentat.git_handler import get_git_diff, get_hexsha_active


def test_get_git_diff(temp_testbed, mock_session_context):
    # Add a new file and commit it, then delete but don't commit
    with open(temp_testbed / "test_file.txt", "w") as f:
        f.write("forty two")
    assert "forty two" in get_git_diff("HEAD")
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "test commit"])
    assert "forty two" not in get_git_diff("HEAD")
    assert "forty two" in get_git_diff("HEAD~1", "HEAD")
    os.remove("test_file.txt")
    assert "forty two" in get_git_diff("HEAD")
    assert "forty two" not in get_git_diff("HEAD~1")


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
