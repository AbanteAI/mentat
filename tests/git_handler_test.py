import os
import subprocess

import pytest

from mentat.git_handler import get_shared_git_root_for_paths


def test_no_paths_given(temp_testbed):
    # Get temp_testbed as the git root when given no paths
    git_root = get_shared_git_root_for_paths([])
    assert git_root == temp_testbed


def test_paths_given(temp_testbed):
    # Get temp_testbed when given directory in temp_testbed
    git_root = get_shared_git_root_for_paths(["scripts"])
    assert git_root == temp_testbed


def test_two_git_roots_given():
    # Exits when given 2 paths with separate git roots
    with pytest.raises(SystemExit) as e_info:
        os.makedirs("git_testing_dir")
        subprocess.run(["git", "init"], cwd="git_testing_dir")

        _ = get_shared_git_root_for_paths(["./", "git_testing_dir"])
    assert e_info.type == SystemExit
