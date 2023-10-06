import asyncio
import json
import os
import shutil
import subprocess
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from textwrap import dedent

import pytest
import tqdm
from git import Repo

from mentat.llm_api import call_llm_api, setup_api_key
from mentat.session import Session
from mentat.session_stream import StreamMessageSource

pytestmark = pytest.mark.benchmark


def exercise_passed(test_output_file, language):
    if not test_output_file.exists():
        return False
    with open(test_output_file, "r") as f:
        lines = f.readlines()
        if language == "python":
            return "failed" not in lines[-1] and "passed" in lines[-1]
        else:
            return "FAIL" not in lines[0] and "PASS" in lines[0]


def get_error_message(test_output_file):
    if not test_output_file.exists():
        return False
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


def get_exercise_file(problem_dir, language):
    problem_file = problem_dir

    match language:
        case "python":
            file_ext = "py"
            problem_file = problem_dir.replace("-", "_")
        case "javascript":
            file_ext = "js"

    exercise_file = f"{problem_file}.{file_ext}"
    return exercise_file


# This will include hint.md
def read_instructions(exercise):
    docs_path = exercise / ".docs"
    instructions = ""
    for file_name in os.listdir(docs_path):
        with open(docs_path / file_name) as f:
            contents = f.read()
            instructions += f"{file_name}\n{contents}\n"
    return instructions


def read_code(problem_dir, language):
    exercise = Path(f"exercises/practice/{problem_dir}")
    code = ""
    exercise_file = get_exercise_file(problem_dir, language)
    with open(exercise / exercise_file) as f:
        contents = f.read()
        code += f"{exercise_file}\n{contents}"
    return code


def read_test_results(exercise):
    with open(exercise / "test_output.txt") as f:
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
    shutil.copyfile(
        f"{os.path.dirname(__file__)}/exercism_benchmark.html",
        f"{local_dir}/results.html",
    )

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


prompt = dedent("""\
    You are a professional code reviewer who helps other coders improve their skills.
    You recently assigned a coder a small coding test to assess their level, with a pre-written stub template
    and an automated test suite to determine if they succeeded.
    They failed the test; using the instructions for the test,
    the code they wrote for the test, and the output of the test suite,
    your job is to determine why they failed. Give a terse but informative couple of sentences
    on why it failed, before giving the reason it failed on the final line in the format
    reason: <reason_failed>
    Your response will be parsed programmatically, so you MUST follow the format for the final line!
    The possible responses for the final line and what they mean are as follows:
    blank (the coder didn't change the file at all from the stub you provided them)
    wording (everything was correct, but the coder messed up the wording or spacing which caused it to be rejected)
    duplication (the coder had a random duplicated line that caused the code to not be compiled/interpreted)
    syntax (the coder messed up their syntax, meaning their code couldn't be compiled/interpreted)
    logic (the coder messed up the logic)
    other (some other reason caused it to fail)""")
model = "gpt-4-0314"


async def failure_analysis(problem_dir, language):
    setup_api_key()
    exercise = Path(f"exercises/practice/{problem_dir}")

    instructions = read_instructions(exercise)
    code = read_code(problem_dir, language)
    test_results = read_test_results(exercise)

    final_message = (
        f"All instructions:\n{instructions}\nCode to review:\n{code}\nTest"
        f" results:\n{test_results}"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": final_message},
    ]
    response = ""
    async for chunk in await call_llm_api(messages, model):
        content = chunk["choices"][0]["delta"].get("content", "")
        response += content

    try:
        reason = response.strip().split("\n")[-1].split()[1]
    except IndexError:
        reason = "error"
    return response, reason


async def send_message(session, message, input_request_message):
    await session.stream.send(
        message,
        source=StreamMessageSource.CLIENT,
        channel=f"input_request:{input_request_message.id}",
    )


async def run_exercise(problem_dir, language="python", max_iterations=2):
    exercise = Path(f"exercises/practice/{problem_dir}")
    exercise_file = exercise / get_exercise_file(problem_dir, language)
    test_output_file = exercise / "test_output.txt"
    session = await Session.create(
        paths=[
            exercise_file,
            exercise / ".docs",
        ],
        exclude_paths=[exercise / ".docs/hints.md"],
        no_code_map=True,
    )
    asyncio.ensure_future(session.start())
    input_request_message = await session.stream.recv("input_request")

    prompt_1 = dedent(
        f"""\
        Use the instructions in exercises/practice/{problem_dir} to modify \
        {exercise_file}. Keep and implement the existing function or class stubs, they will be \
        called from unit tests. Only use standard libraries, don't suggest installing any packages."""
    )
    prompt_2 = dedent(f"""\
        See the testing errors above.
        The tests are correct.
        Fix the code in {exercise_file} to resolve the errors.""")

    iterations = 0
    while iterations < max_iterations:
        if exercise_passed(test_output_file, language):
            break
        message = (
            prompt_1
            if iterations == 0
            else get_error_message(test_output_file) + prompt_2
        )
        await send_message(session, message, input_request_message)
        input_request_message = await session.stream.recv("input_request")
        await send_message(session, "y", input_request_message)
        input_request_message = await session.stream.recv("input_request")

        run_exercise_test(exercise, test_output_file, language)
        iterations += 1

    await session.stop()
    passed = exercise_passed(test_output_file, language)
    result = {
        "iterations": iterations,
        "passed": passed,
        "test": problem_dir,
    }
    if not result["passed"]:
        response, reason = await failure_analysis(problem_dir, language)
        result["response"] = response
        result["reason"] = reason
    result["instructions"] = read_instructions(exercise)
    result["code"] = read_code(problem_dir, language)
    return result


def run_exercise_sync(problem_dir, language="python", max_iterations=2):
    try:
        return asyncio.run(run_exercise(problem_dir, language, max_iterations))
    except Exception as e:
        print(f"\nError running {problem_dir}")
        print(str(e), flush=True)
        return {
            "iterations": None,
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

        # Update the html file
        results_json = list(map(json.dumps, results))
        results_str = "[" + ",".join(results_json) + "]"
        with open("results.html", "r") as f:
            html = f.read()
        html = html.replace("{{ results }}", results_str)
        with open("results.html", "w") as f:
            f.write(html)
