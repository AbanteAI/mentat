import concurrent.futures
import os
import subprocess
import threading
import time

import pytest
from git import Repo

from mentat.app import run
from mentat.user_input_manager import UserInputManager, UserQuitInterrupt

threadLocal = threading.local()


def exercise_passed():
    try:
        with open(threadLocal.test_output_file, "r") as f:
            lines = f.readlines()
            return not "failed" in lines[-1] and "passed" in lines[-1]
    except:
        return False


def get_error_message():
    with open(threadLocal.test_output_file, "r") as f:
        lines = f.readlines()
        if len(lines) > 30:
            lines = lines[-30:]
        return "\n".join(lines)


@pytest.fixture
def mock_user_input_manager(max_iterations, mocker):
    def mocked_collect_user_input(self, use_plain_session: bool = False) -> str:
        if not hasattr(self, "call_count"):
            self.call_count = 0
        self.call_count += 1

        if self.call_count == 1:
            return "Please complete the stub program you have been given."
        elif self.call_count == 2:
            return "y"
        else:
            results = subprocess.run(
                ["pytest", threadLocal.exercise], stdout=subprocess.PIPE
            )
            with open(threadLocal.test_output_file, "w") as f:
                f.write(results.stdout.decode("utf-8"))
            if exercise_passed() or threadLocal.iterations >= max_iterations:
                raise UserQuitInterrupt()
            if threadLocal.confirm:
                threadLocal.confirm = False
                return "y"
            else:
                threadLocal.iterations += 1
                threadLocal.confirm = True
                return (
                    "When I ran the test I got the following error message. Can you try again?\n"
                    + get_error_message()
                )

    mocker.patch.object(
        UserInputManager, "collect_user_input", new=mocked_collect_user_input
    )


@pytest.fixture
def clone_exercism_python_repo():
    exercism_url = "https://github.com/exercism/python.git"
    local_dir = "../exercism-python"
    if os.path.exists(local_dir):
        repo = Repo(local_dir)
        repo.git.reset("--hard")
        repo.remotes.origin.pull()
    else:
        repo = Repo.clone_from(exercism_url, local_dir)
    # Mentat uses git history so running this test from mentat/ can lead to errors.
    os.chdir(f"{local_dir}/exercises/practice")


@pytest.fixture
def num_exercises(request):
    return int(request.config.getoption("--num_exercises"))


@pytest.fixture
def max_iterations(request):
    return int(request.config.getoption("--max_iterations"))


@pytest.fixture
def max_workers(request):
    return int(request.config.getoption("--max_workers"))


def run_exercise(problem_dir):
    threadLocal.test_output_file = f"{problem_dir}/test_output.txt"
    threadLocal.exercise = problem_dir
    threadLocal.iterations = 1
    threadLocal.confirm = False
    time.sleep(0.3)
    run(
        [problem_dir],
        exclude_paths=[
            f"{problem_dir}/.meta",
            f"{problem_dir}/.approaches",
            f"{problem_dir}/.docs",
            f"{problem_dir}/{problem_dir}_test.py",
        ],
        no_code_map=True,
    )
    return {
        "iterations": threadLocal.iterations,
        "passed": exercise_passed(),
        "test": problem_dir,
    }


def test_practice_directory_performance(
    mock_user_input_manager,
    clone_exercism_python_repo,
    num_exercises,
    max_iterations,
    max_workers,
):
    exercises = os.listdir(".")[:num_exercises]

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(run_exercise, exercises))
        print("Results: ", results)
        first_iteration = len(
            [
                result
                for result in results
                if result["iterations"] == 1 and result["passed"]
            ]
        )
        eventually = len([result for result in results if result["passed"]])
        print(
            f"Results: {first_iteration}/{num_exercises} passed in the first attempt and {eventually}/{num_exercises} passed in {max_iterations} attempts"
        )
