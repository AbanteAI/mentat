#!/usr/bin/env python
import asyncio
import multiprocessing
import os
from functools import partial
from pathlib import Path

import tqdm
from openai import BadRequestError

from benchmarks.arg_parser import common_benchmark_parser
from benchmarks.benchmark_result import BenchmarkResult
from benchmarks.benchmark_result_summary import BenchmarkResultSummary
from benchmarks.exercise_runners.exercise_runner_factory import ExerciseRunnerFactory
from mentat.config import Config
from mentat.python_client.client import PythonClient
from mentat.sampler.utils import clone_repo
from mentat.session_context import SESSION_CONTEXT


def clone_exercism_repo(refresh_repo, language):
    exercism_url = f"https://github.com/exercism/{language}.git"
    local_dir = clone_repo(exercism_url, f"exercism-{language}", refresh_repo)
    os.chdir(local_dir)


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
    client = PythonClient(
        cwd=Path("."),
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
    old_result = exercise_runner.get_result_from_txt()
    if old_result:
        return old_result
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
    with open("results.txt", "a") as f:
        f.write(result.to_json())
        f.write("\n")
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


def run_exercism_benchmark(
    benchmarks,
    max_benchmarks,
    max_iterations,
    max_workers,
    language,
):
    all_exercises = os.listdir("exercises/practice")
    if len(benchmarks) > 0:
        exercises = list(set(benchmarks) & set(all_exercises))
    else:
        exercises = all_exercises[:max_benchmarks]
    exercises = sorted(exercises)
    num_exercises = len(exercises)

    # TODO: aiomultiprocessing would be faster with fewer workers; setup a Manager in a parent process
    # that controls the children processes so that we don't run into rate limits
    with multiprocessing.Pool(processes=max_workers) as pool:
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
            pbar.set_description(tqdm_summary(results) + "| Last Ran: " + result.name)
        results.sort(key=lambda result: result.name)

        summary = BenchmarkResultSummary(results)
        with open("results.json", "w") as f:
            f.write(summary.to_json())
        summary.render_results()


if __name__ == "__main__":
    parser = common_benchmark_parser()
    args = parser.parse_args()
    clone_exercism_repo(args.refresh_repo, args.language)
    print(args)
    run_exercism_benchmark(
        args.benchmarks,
        args.max_benchmarks,
        args.max_iterations,
        args.max_workers,
        args.language,
    )
