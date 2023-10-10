import asyncio
import json
import os
import webbrowser
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import pytest
import tqdm
from git import Repo
from openai import InvalidRequestError

from mentat.llm_api import COST_TRACKER, call_llm_api, setup_api_key
from mentat.session import Session
from mentat.session_stream import StreamMessageSource

from .exercise_runners.exercise_runner_factory import ExerciseRunnerFactory

pytestmark = pytest.mark.benchmark


# This will include hint.md
def read_instructions(exercise_runner):
    docs_path = Path(f"{exercise_runner.exercise_dir}/.docs")
    instructions = ""
    for file_name in os.listdir(docs_path):
        with open(docs_path / file_name) as f:
            contents = f.read()
            instructions += f"{file_name}\n{contents}\n"
    return instructions


def read_code(exercise_runner, language):
    code = ""
    with open(exercise_runner.exercise_full_path) as f:
        contents = f.read()
        code += f"{exercise_runner.exercise_file}\n{contents}"
    return code


def read_test_results(exercise_runner):
    if not os.path.exists(exercise_runner.test_output_file):
        return ""
    with open(exercise_runner.test_output_file) as f:
        contents = f.read()
        test_results = f"test_output.txt\n{contents}"
    return test_results


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


prompt = (
    "You are a professional code reviewer who helps other coders improve their skills."
    + "You recently assigned a coder a small coding test to assess their level, with a"
    " pre-written stub template"
    + "and an automated test suite to determine if they succeeded."
    + "They failed the test; using the instructions for the test,"
    + "the code they wrote for the test, and the output of the test suite,"
    + "your job is to determine why they failed. Give a terse but informative couple of"
    " sentences"
    + "on why it failed, before giving the reason it failed on the final line in the"
    " format"
    + "reason: <reason_failed>"
    + "Your response will be parsed programmatically, so you MUST follow the format for"
    " the final line!"
    + "The possible responses for the final line and what they mean are as follows:"
    + "blank (the coder didn't change the file at all from the stub you provided them)"
    + "wording (everything was correct, but the coder messed up the wording or spacing"
    " which caused it to be rejected)"
    + "duplication (the coder had a random duplicated line that caused the code to not"
    " be compiled/interpreted)"
    + "syntax (the coder messed up their syntax, meaning their code couldn't be"
    " compiled/interpreted)"
    + "logic (the coder messed up the logic)"
    + "other (some other reason caused it to fail)"
)
model = "gpt-4-0314"


async def failure_analysis(exercise_runner, language):
    setup_api_key()

    instructions = read_instructions(exercise_runner)
    code = read_code(exercise_runner, language)
    test_results = read_test_results(exercise_runner)

    final_message = (
        f"All instructions:\n{instructions}\nCode to review:\n{code}\nTest"
        f" results:\n{test_results}"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": final_message},
    ]
    response = ""
    try:
        async for chunk in await call_llm_api(messages, model):
            content = chunk["choices"][0]["delta"].get("content", "")
            response += content
    except InvalidRequestError:
        response = "Unable to analyze test case\nreason: too many tokens to analyze"

    try:
        reason = response.strip().split("\n")[-1].split()[1]
    except IndexError:
        reason = "response error"
    return response, reason


async def send_message(session, message, input_request_message):
    await session.stream.send(
        message,
        source=StreamMessageSource.CLIENT,
        channel=f"input_request:{input_request_message.id}",
    )


async def run_exercise(problem_dir, language="python", max_iterations=2):
    exercise_runner = ExerciseRunnerFactory.create(language, problem_dir)
    if exercise_runner.already_ran():
        old_result = get_result_from_txt(exercise_runner)
        if old_result:
            return old_result
    session = await Session.create(
        paths=[
            Path(exercise_runner.exercise_full_path),
            Path(f"{exercise_runner.exercise_dir}/.docs"),
        ],
        exclude_paths=[Path(f"{exercise_runner.exercise_dir}/.docs/hints.md")],
        no_code_map=True,
    )
    asyncio.ensure_future(session.start())
    input_request_message = await session.stream.recv("input_request")

    prompt_1 = (
        f"Use the instructions in {exercise_runner.exercise_dir}/.docs to modify"
        + f" {exercise_runner.exercise_file}. Keep and implement the existing"
        + " function or class stubs, they will be called from unit tests. Only use"
        + f" standard {language} libraries, don't suggest installing any packages."
    )
    prompt_2 = (
        "\nSee the testing errors above. The tests are correct. Fix the code"
        + f" in {exercise_runner.exercise_file} to resolve the errors."
    )

    iterations = 0
    while iterations < max_iterations:
        if exercise_runner.exercise_passed():
            break
        message = (
            prompt_1
            if iterations == 0
            else exercise_runner.get_error_message() + prompt_2
        )
        await send_message(session, message, input_request_message)
        input_request_message = await session.stream.recv("input_request")
        await send_message(session, "y", input_request_message)
        input_request_message = await session.stream.recv("input_request")

        exercise_runner.run_test()
        iterations += 1

    await session.stop()
    passed = exercise_runner.exercise_passed()
    result = {
        "iterations": iterations,
        "passed": passed,
        "test": problem_dir,
    }
    if not result["passed"]:
        response, reason = await failure_analysis(exercise_runner, language)
        result["response"] = response
        result["reason"] = reason
    result["tokens"] = COST_TRACKER.get().total_tokens
    return result


def run_exercise_sync(problem_dir, language="python", max_iterations=2):
    exercise_runner = ExerciseRunnerFactory.create(language, problem_dir)
    try:
        result = asyncio.run(run_exercise(problem_dir, language, max_iterations))
    except Exception as e:
        print(f"\nError running {problem_dir}")
        print(str(e), flush=True)
        result = {
            "iterations": 0,
            "passed": False,
            "test": problem_dir,
            "response": str(e),
            "reason": "error",
            "tokens": 0,
        }
    result["instructions"] = read_instructions(exercise_runner)
    result["code"] = read_code(exercise_runner, language)
    result["test-output"] = read_test_results(exercise_runner)
    return result


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


def get_result_from_txt(problem_dir):
    with open("results.txt", "r") as f:
        for line in f.readlines():
            if f'"{problem_dir}"' in line:
                return json.loads(line)


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

        result_map = pool.imap(
            partial(
                run_exercise_sync, language=language, max_iterations=max_iterations
            ),
            exercises,
        )
        results = []
        for result in result_map:
            pbar.update()
            results.append(result)
            with open("results.txt", "a") as f:
                json.dump(result, f)
                f.write("\n")
            pbar.set_description(
                summarize_results(results) + "| Last Ran: " + result["test"]
            )
        results.sort(key=lambda result: result["test"])

        # Update the html file
        results_json = list(map(json.dumps, results))
        results_str = "[" + ",".join(results_json) + "]"
        with open(f"{os.path.dirname(__file__)}/exercism_benchmark.html", "r") as f:
            html = f.read()
        html = html.replace("{{ results }}", results_str)
        with open("results.html", "w") as f:
            f.write(html)
        webbrowser.open("file://" + os.path.realpath("results.html"))
