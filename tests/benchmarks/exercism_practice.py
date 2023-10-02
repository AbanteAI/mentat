import os
from uuid import uuid4
import subprocess
import sys
import threading
from functools import partial
from aiomultiprocess import Pool
from pathlib import Path
from textwrap import dedent

import pytest
import tqdm
from git import Repo

from mentat.session import Session
from mentat.session_stream import StreamMessage, StreamMessageSource

threadLocal = threading.local()

pytestmark = pytest.mark.benchmark


def exercise_passed(language):
    try:
        with open(threadLocal.test_output_file, "r") as f:
            lines = f.readlines()
            if language == "python":
                return "failed" not in lines[-1] and "passed" in lines[-1]
            else:
                return "FAIL" not in lines[0] and "PASS" in lines[0]
    except FileNotFoundError:
        return False


def get_error_message():
    with open(threadLocal.test_output_file, "r") as f:
        lines = f.readlines()
        lines = lines[:50]
        return "\n".join(lines)


def run_exercise_test(language):
    try:
        if language == "python":
            proc = subprocess.run(
                ["pytest", threadLocal.exercise], stdout=subprocess.PIPE, timeout=5
            )
        else:
            proc = subprocess.run(
                ["./node_modules/jest/bin/jest.js", threadLocal.exercise],
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                timeout=5,
            )
        results = proc.stdout.decode("utf-8")
    except subprocess.TimeoutExpired:
        results = "Test timed out"
    with open(threadLocal.test_output_file, "w") as f:
        f.write(results)


def wrap(value):
    return StreamMessage(
        id=uuid4(),
        channel="default",
        source=StreamMessageSource.CLIENT,
        data=value,
        extra=None,
        created_at=datetime.utcnow(),
    )

@pytest.fixture
def mock_user_input_manager(max_iterations, mocker, language):
    async def mocked_collect_user_input():
        if threadLocal.iterations == 0:
            threadLocal.iterations = 1
            threadLocal.confirm = True
            return wrap(dedent(
                f"""\
                Use the instructions in {threadLocal.exercise}/.docs to modify \
                {threadLocal.exercise_file}. Keep and implement the existing function or class stubs, they will be \
                called from unit tests. Only use standard libraries, don't suggest installing any packages."""
            ))
        else:
            if threadLocal.confirm:
                threadLocal.confirm = False
                return wrap("y")
            run_exercise_test(language)
            if threadLocal.iterations >= max_iterations or exercise_passed(language):
                return wrap("q")
            else:
                threadLocal.iterations += 1
                threadLocal.confirm = True
                return wrap(get_error_message() + dedent(
                    f"""
                    See the testing errors above.
                    The tests are correct.
                    Fix the code in {threadLocal.exercise_file} to resolve the errors."""
                ))

    print("We're mocking")
    mocker.patch("mentat.code_edit_feedback.collect_user_input", new=mocked_collect_user_input)
    mocker.patch("mentat.session_input.collect_user_input", new=mocked_collect_user_input)
    mocker.patch("mentat.session.collect_user_input", new=mocked_collect_user_input)


@pytest.fixture
def clone_exercism_repo(refresh_repo, language):
    exercism_url = f"https://github.com/exercism/{language}.git"

    local_dir = f"{os.path.dirname(__file__)}/../../../exercism-{language}"
    if os.path.exists(local_dir):
        if refresh_repo:
            repo = Repo(local_dir)
            repo.git.reset("--hard")
            repo.git.clean("-fd")
            repo.remotes.origin.pull()
    else:
        repo = Repo.clone_from(exercism_url, local_dir)
    os.chdir(local_dir)
    if language == "javascript":
        subprocess.run(["npm", "install"], stdout=subprocess.PIPE)


@pytest.fixture
def max_exercises(request):
    return int(request.config.getoption("--max_exercises"))


@pytest.fixture
def max_iterations(request):
    return int(request.config.getoption("--max_iterations"))


@pytest.fixture
def refresh_repo(request):
    return request.config.getoption("--refresh_repo")


@pytest.fixture
def max_workers(request):
    return int(request.config.getoption("--max_workers"))


@pytest.fixture
def language(request):
    return request.config.getoption("--language")


async def run_exercise(problem_dir, language="python"):
    try:
        if language == "python":
            file_ext = "py"
        else:
            file_ext = "js"
        threadLocal.exercise = f"exercises/practice/{problem_dir}"
        if language == "python":
            problem_file = problem_dir.replace("-", "_")
        else:
            problem_file = problem_dir
        threadLocal.exercise_file = f"{threadLocal.exercise}/{problem_file}.{file_ext}"
        threadLocal.test_output_file = f"{threadLocal.exercise}/test_output.txt"
        threadLocal.iterations = 0
        if os.path.exists(threadLocal.test_output_file):
            passed = exercise_passed(language)
            return {
                "iterations": None,
                "passed": passed,
                "test": problem_dir,
            }


        session = await Session.create(
            paths=[
                Path(threadLocal.exercise_file),
                Path(f"{threadLocal.exercise}/.docs"),
            ],
            exclude_paths=[Path(f"{threadLocal.exercise}/.docs/hints.md")],
            no_code_map=True,
        )
        await session.start()
        await session.stream.stop()
        passed = exercise_passed(language)
        return {
            "iterations": threadLocal.iterations,
            "passed": passed,
            "test": problem_dir,
        }
    except Exception as e:
        sys.__stdout__.write(f"\nError running {problem_dir}")
        sys.__stdout__.write(str(e))
        return {
            "iterations": threadLocal.iterations,
            "passed": False,
            "test": problem_dir,
        }


def summarize_results(results):
    passed_in_n = {}
    failed = 0
    for result in results:
        if result["passed"]:
            iteration = result["iterations"]
            if iteration:
                passed_in_n[iteration] = passed_in_n.get(iteration, 0) + 1
        else:
            failed += 1
    return "Passed: " + str(passed_in_n)[1:-1] + "| Failed: " + str(failed)


@pytest.mark.asyncio
async def test_practice_directory_performance(
    mock_user_input_manager,
    clone_exercism_repo,
    max_exercises,
    max_iterations,
    max_workers,
    language,
):
    exercises = os.listdir("exercises/practice")[:max_exercises]
    num_exercises = len(exercises)
    # sys.stdout = open("mentat_output.txt", "w")

    async with Pool(processes=max_workers) as pool:
        # results = []
        # pbar = tqdm.tqdm(
            # total=num_exercises,
        # )
        results = await pool.map(partial(run_exercise, language=language), exercises),
        for result in results:
            results.append(result)
            with open("results.txt", "a") as f:
                f.write(f"{result}\n")
            # pbar.set_description(
                # summarize_results(results) + "| Last Ran: " + result["test"]
            # )
        # sys.stdout.close()
        # sys.stdout = sys.__stdout__
        print(f"Results: {results}")
