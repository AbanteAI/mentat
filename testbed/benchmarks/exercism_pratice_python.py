import os

import pytest
from git import Repo
from prompt_toolkit import PromptSession

from mentat.app import run


@pytest.fixture
def mock_prompt_session_prompt(mocker):
    mock_method = mocker.MagicMock()
    # Mock the super().prompt that MentatPromptSession calls
    mocker.patch.object(PromptSession, "prompt", new=mock_method)
    return mock_method


exercism_url = "https://github.com/exercism/python.git"
local_dir = "exercism-python"


@pytest.fixture
def clone_exercism_python_repo():
    if os.path.exists(local_dir):
        repo = Repo(local_dir)
        repo.git.reset("--hard")
        repo.remotes.origin.pull()
    else:
        repo = Repo.clone_from(exercism_url, local_dir)


def test_practice_directory_performance(
    mock_prompt_session_prompt, clone_exercism_python_repo
):
    # Structured this way so it's easy to run on subsets
    num_to_run = 134
    passed = 0
    failed = 0

    os.chdir(f"{local_dir}/exercises/practice")

    # TODO: run in parallel
    for problem_dir in os.listdir("."):
        if num_to_run == 0:
            break
        mock_prompt_session_prompt.side_effect = [
            "Please complete the stub program you have been given.",
            "y",
            KeyboardInterrupt,
        ]
        # TODO: change the following line to exclude files that contain the word test. Or do it both ways
        # TODO: exclude all paths that start with dot
        run(
            [problem_dir],
            exclude_paths=[f"{problem_dir}/.docs", f"{problem_dir}/.meta"],
            no_code_map=True,
        )
        test = None
        for file in os.listdir(problem_dir):
            if file.endswith("_test.py"):
                test = file
                break
        if test:
            # TODO: get error and feed back in to give mentat another chance.
            results = pytest.main([f"{problem_dir}/{test}"])
            print(results)
            if results == 0:
                passed += 1
            else:
                failed += 1
        else:
            print(f"Could not find test for {problem_dir}")
        num_to_run -= 1

    # TODO: I'm not sure it makes sense to run with pytest because it's not so much
    # a pass fail script as something to collect a variety of statistics. I may refactor into a scipt.
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
