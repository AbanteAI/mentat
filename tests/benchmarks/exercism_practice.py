import asyncio
import os
import subprocess
import sys
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from textwrap import dedent

import pytest
import tqdm
from git import Repo

from mentat.python_client.client import PythonClient

pytestmark = pytest.mark.benchmark


def exercise_passed(test_output_file, language):
    try:
        with open(test_output_file, "r") as f:
            lines = f.readlines()
            if language == "python":
                return "failed" not in lines[-1] and "passed" in lines[-1]
            else:
                return "FAIL" not in lines[0] and "PASS" in lines[0]
    except FileNotFoundError:
        return False


def get_error_message(test_output_file):
    with open(test_output_file, "r") as f:
        lines = f.readlines()
        lines = lines[:50]
        return "\n".join(lines)


def run_exercise_test(exercise, test_output_file, language):
    try:
        if language == "python":
            proc = subprocess.run(
                ["pytest", exercise], stdout=subprocess.PIPE, timeout=5
            )
        else:
            proc = subprocess.run(
                ["./node_modules/jest/bin/jest.js", exercise],
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                timeout=5,
            )
        results = proc.stdout.decode("utf-8")
    except subprocess.TimeoutExpired:
        results = "Test timed out"
    with open(test_output_file, "w") as f:
        f.write(results)


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
def exercises(request):
    exercises = request.config.getoption("--exercises")
    if len(exercises) == 1:
        return exercises[0]
    return exercises


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


async def run_exercise(problem_dir, language="python", max_iterations=2):
    try:
        if language == "python":
            file_ext = "py"
        else:
            file_ext = "js"
        exercise = f"exercises/practice/{problem_dir}"
        if language == "python":
            problem_file = problem_dir.replace("-", "_")
        else:
            problem_file = problem_dir
        exercise_file = f"{exercise}/{problem_file}.{file_ext}"
        test_output_file = f"{exercise}/test_output.txt"
        if os.path.exists(test_output_file):
            passed = exercise_passed(test_output_file, language)
            return {
                "iterations": None,
                "passed": passed,
                "test": problem_dir,
            }

        client = PythonClient(
            paths=[
                Path(exercise_file),
                Path(f"{exercise}/.docs"),
            ],
            exclude_paths=[Path(f"{exercise}/.docs/hints.md")],
            no_code_map=True,
        )

        await client.call_mentat_auto_accept(
            dedent(
                f"""\
                    Use the instructions in exercises/practice/{problem_dir} to modify \
                    {exercise_file}. Keep and implement the existing function or class stubs, they will be \
                    called from unit tests. Only use standard libraries, don't suggest installing any packages."""
            )
        )
        iterations = 1
        run_exercise_test(exercise, test_output_file, language)
        while iterations < max_iterations:
            if exercise_passed(test_output_file, language):
                break
            await client.call_mentat_auto_accept(
                get_error_message(test_output_file) + dedent(f"""
                        See the testing errors above.
                        The tests are correct.
                        Fix the code in {exercise_file} to resolve the errors.""")
            )
            run_exercise_test(exercise, test_output_file, language)
            iterations += 1

        await client.stop()
        passed = exercise_passed(test_output_file, language)
        return {
            "iterations": iterations,
            "passed": passed,
            "test": problem_dir,
        }
    except Exception as e:
        sys.__stdout__.write(f"\nError running {problem_dir}")
        sys.__stdout__.write(str(e))
        return {
            "iterations": iterations,
            "passed": False,
            "test": problem_dir,
        }


def run_exercise_sync(problem_dir, language="python", max_iterations=2):
    return asyncio.run(run_exercise(problem_dir, language, max_iterations))


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


def test_practice_directory_performance(
    clone_exercism_repo,
    exercises,
    max_exercises,
    max_iterations,
    max_workers,
    language,
):
    all_exercises = os.listdir("exercises/practice")
    if len(exercises) > 0:
        exercises = set(exercises) & set(all_exercises)
    else:
        exercises = all_exercises[:max_exercises]
    num_exercises = len(exercises)

    # TODO: aiomultiprocessing would be faster with fewer workers; setup a Manager in a parent process
    # that controls the children processes so that we don't run into rate limits
    with Pool(processes=max_workers) as pool:
        pbar = tqdm.tqdm(total=num_exercises)

        result_map = pool.map(
            partial(
                run_exercise_sync, language=language, max_iterations=max_iterations
            ),
            exercises,
        )
        results = []
        for result in result_map:
            results.append(result)
            pbar.update()
            with open("results.txt", "a") as f:
                f.write(f"{result}\n")
            pbar.set_description(
                summarize_results(results) + "| Last Ran: " + result["test"]
            )
        print(f"Results: {results}")
