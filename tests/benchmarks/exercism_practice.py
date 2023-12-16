import asyncio
import os
import webbrowser
from functools import partial
from multiprocessing import Pool

import pytest
import tqdm
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import BadRequestError

from mentat.config import Config
from mentat.python_client.client import PythonClient
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import clone_repo
from tests.benchmarks.benchmark_result import BenchmarkResult
from tests.benchmarks.exercise_runners.exercise_runner_factory import (
    ExerciseRunnerFactory,
)

pytestmark = pytest.mark.benchmark


@pytest.fixture
def clone_exercism_repo(refresh_repo, language):
    exercism_url = f"https://github.com/exercism/{language}.git"
    local_dir = clone_repo(exercism_url, f"exercism-{language}", refresh_repo)
    os.chdir(local_dir)


@pytest.fixture
def max_iterations(request):
    return int(request.config.getoption("--max_iterations"))


@pytest.fixture
def max_workers(request):
    return int(request.config.getoption("--max_workers"))


@pytest.fixture
def language(request):
    return request.config.getoption("--language")


prompt = (
    "You are a professional code reviewer who helps other coders improve their skills."
    " You recently assigned a coder a small coding test to assess their level, with a"
    " pre-written stub template and an automated test suite to determine if they"
    " succeeded. They failed the test; using the instructions for the test, the code"
    " they wrote for the test, and the output of the test suite, your job is to"
    " determine why they failed. Give a terse but informative couple of sentences on"
    " why they failed, before giving the reason it failed on the final line in the"
    " format:\n"
    + "reason: <reason_failed>\n"
    + "Your response will be parsed programmatically, so you MUST follow the format for"
    " the final line! The possible responses for the final line and what they mean"
    " are as follows:\n"
    + "blank (the coder didn't change the file at all from the stub you provided"
    " them)\n"
    + "wording (everything was correct, but the coder messed up the wording or spacing"
    " which caused it to be rejected)\n"
    + "duplication (the coder had a random duplicated line that caused the code to not"
    " be compiled/interpreted)\n"
    + "syntax (the coder messed up their syntax, meaning their code couldn't be"
    " compiled/interpreted)\n"
    + "logic (the coder messed up the logic)\n"
    + "other (some other reason caused it to fail)\n"
)
model = "gpt-4-0314"


async def failure_analysis(exercise_runner, language):
    instructions = exercise_runner.read_instructions()
    code = exercise_runner.read_code(language)
    test_results = exercise_runner.read_test_results()

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
        llm_api_handler = SESSION_CONTEXT.get().llm_api_handler
        llm_grade = await llm_api_handler.call_llm_api(messages, model, False)
        response = llm_grade.choices[0].message.content
    except BadRequestError:
        response = "Unable to analyze test case\nreason: too many tokens to analyze"

    try:
        reason = response.strip().split("\n")[-1][8:]
    except IndexError:
        reason = "response error"
    return response, reason


async def run_exercise(problem_dir, language="python", max_iterations=2):
    exercise_runner = ExerciseRunnerFactory.create(language, problem_dir)
    old_result = exercise_runner.get_result_from_txt()
    if old_result:
        return old_result
    client = PythonClient(
        paths=exercise_runner.include_files(),
        exclude_paths=exercise_runner.exclude_files(),
        config=Config(),
    )
    await client.startup()

    # These prompts are copied from Aider: https://aider.chat/docs/benchmarks.html to
    # allow for direct comparison.
    prompt_1 = (
        f"Use the instructions in {exercise_runner.docs()} to modify"
        + f" {exercise_runner.file}. Keep and implement the existing"
        + " function or class stubs, they will be called from unit tests. Only use"
        + f" standard {language} libraries, don't suggest installing any packages."
    )
    prompt_2 = (
        "\nSee the testing errors above. The tests are correct. Fix the code"
        + f" in {exercise_runner.file} to resolve the errors."
    )

    iterations = 0
    while iterations < max_iterations and not client.stopped.is_set():
        if exercise_runner.passed():
            break
        message = (
            prompt_1
            if iterations == 0
            else exercise_runner.get_error_message() + prompt_2
        )
        await client.call_mentat_auto_accept(message)
        await client.wait_for_edit_completion()

        exercise_runner.run_test()
        iterations += 1

    had_error = client.stopped.is_set()
    messages = client.get_conversation().literal_messages
    await client.shutdown()
    passed = exercise_runner.passed()
    cost_tracker = SESSION_CONTEXT.get().cost_tracker
    result = BenchmarkResult(
        iterations=iterations,
        passed=passed,
        name=exercise_runner.name,
        tokens=cost_tracker.total_tokens,
        cost=cost_tracker.total_cost,
        transcript={"id": problem_dir, "messages": messages},
    )
    if had_error:
        result.response = "Error while running mentat"
        result.reason = "error"
    elif not result.passed:
        response, reason = await failure_analysis(exercise_runner, language)
        result.response = response
        result.reason = reason
    return result


def run_exercise_sync(problem_dir, language="python", max_iterations=2):
    exercise_runner = ExerciseRunnerFactory.create(language, problem_dir)
    try:
        result = asyncio.run(run_exercise(problem_dir, language, max_iterations))
    except Exception as e:
        print(f"\nError running {problem_dir}")
        print(str(e), flush=True)
        result = BenchmarkResult(
            iterations=0,
            passed=False,
            name=problem_dir,
            tokens=0,
            cost=0,
            response=str(e),
            reason="error",
            transcript={"id": problem_dir, "messages": []},
        )
    result.instructions = exercise_runner.read_instructions()
    result.code = exercise_runner.read_code(language)
    result.test_output = exercise_runner.read_test_results()
    return result


def tqdm_summary(results):
    passed_in_n = {}
    failed = 0
    for result in results:
        if result.passed:
            iteration = result.iterations
            if iteration:
                passed_in_n[iteration] = passed_in_n.get(iteration, 0) + 1
        else:
            failed += 1
    return "Passed: " + str(passed_in_n)[1:-1] + "| Failed: " + str(failed)


def results_summary(results):
    results_map = {}
    passedIterations = {}
    reasons = {}
    passed = 0
    failed = 0
    tokens = 0
    cost = 0
    totalIterations = 0

    for result in results:
        name = result.name
        cost += result.cost
        results_map[name] = result
        if result.passed:
            passed += 1
            iterations = result.iterations
            passedIterations[iterations] = passedIterations.get(iterations, 0) + 1
            tokens += result.tokens
            totalIterations += iterations
        else:
            failed += 1
            reason = result.reason
            reasons[reason] = reasons.get(reason, 0) + 1

    avgTokens = tokens // totalIterations if totalIterations > 0 else 0
    return {
        "cost": cost,
        "results_map": results_map,
        "passedIterations": passedIterations,
        "reasons": reasons,
        "passed": passed,
        "failed": failed,
        "avgTokens": avgTokens,
    }


def test_practice_directory_performance(
    clone_exercism_repo,
    benchmarks,
    max_benchmarks,
    max_iterations,
    max_workers,
    language,
):
    all_exercises = os.listdir("exercises/practice")
    if len(benchmarks) > 0:
        exercises = set(benchmarks) & set(all_exercises)
    else:
        exercises = all_exercises[:max_benchmarks]
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
                f.write(result.to_json())
                f.write("\n")
            pbar.set_description(tqdm_summary(results) + "| Last Ran: " + result.name)
        results.sort(key=lambda result: result.name)

        env = Environment(
            loader=FileSystemLoader(
                os.path.join(
                    os.path.dirname(__file__), "../../mentat/resources/templates"
                )
            ),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template = env.get_template("exercism_benchmark.jinja")
        summary = results_summary(results)
        rendered_html = template.render(summary=summary)

        with open("results.html", "w") as f:
            f.write(rendered_html)
        webbrowser.open("file://" + os.path.realpath("results.html"))
