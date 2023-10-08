import asyncio
import os
import sys
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from textwrap import dedent

import pytest
import tqdm
from git import Repo

from mentat.session import Session
from mentat.session_stream import StreamMessageSource

from .exercise_runners.exercise_runner_factory import ExerciseRunnerFactory

pytestmark = pytest.mark.benchmark


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
        exercise_runner = ExerciseRunnerFactory.create(language, problem_dir)
        if exercise_runner.already_ran():
            return {"skipped": True, "test": problem_dir}

        session = await Session.create(
            paths=[
                Path(exercise_runner.exercise_file),
                Path(f"{exercise_runner.exercise_dir}/.docs"),
            ],
            exclude_paths=[Path(f"{exercise_runner.exercise_dir}/.docs/hints.md")],
            no_code_map=True,
        )
        asyncio.ensure_future(session.start())

        input_request_message = await session.stream.recv("input_request")
        await session.stream.send(
            f"Use the instructions in {exercise_runner.exercise_dir}/.docs to modify"
            f" {exercise_runner.exercise_file}. Keep and implement the existing"
            " function or class stubs, they will be called from unit tests. Only use"
            f" standard {language} libraries, don't suggest installing any packages.",
            source=StreamMessageSource.CLIENT,
            channel=f"input_request:{input_request_message.id}",
        )
        input_request_message = await session.stream.recv("input_request")
        await session.stream.send(
            "y",
            source=StreamMessageSource.CLIENT,
            channel=f"input_request:{input_request_message.id}",
        )
        input_request_message = await session.stream.recv("input_request")
        iterations = 1
        exercise_runner.run_test()
        while iterations < max_iterations:
            if exercise_runner.exercise_passed():
                break
            await session.stream.send(
                exercise_runner.get_error_message()
                + "\nSee the testing errors above. The tests are correct. Fix the code"
                f" in {exercise_runner.exercise_file} to resolve the errors.",
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )
            input_request_message = await session.stream.recv("input_request")
            await session.stream.send(
                "y",
                source=StreamMessageSource.CLIENT,
                channel=f"input_request:{input_request_message.id}",
            )
            input_request_message = await session.stream.recv("input_request")
            exercise_runner.run_test()
            iterations += 1

        await session.stop()
        passed = exercise_runner.exercise_passed()
        return {
            "iterations": iterations,
            "passed": passed,
            "test": problem_dir,
        }
    except Exception as e:
        sys.__stdout__.write(f"\nError running {exercise_runner.exercise}")
        sys.__stdout__.write(str(e))
        return {"error": True, "test": problem_dir}


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
            if result.get("skipped") or result.get("error"):
                print(result)
                pbar.update()
                continue
            results.append(result)
            pbar.update()
            with open("results.txt", "a") as f:
                f.write(f"{result}\n")
            pbar.set_description(
                summarize_results(results) + "| Last Ran: " + result["test"]
            )
        print(f"Results: {results}")
