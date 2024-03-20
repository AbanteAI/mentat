#!/usr/bin/env python
import asyncio
import json
import os
import subprocess
from itertools import islice
from pathlib import Path
from textwrap import dedent

from git import Repo
from openai import OpenAI

from benchmarks.arg_parser import common_benchmark_parser
from mentat import Mentat
from mentat.sampler.utils import clone_repo


def load_tests(benchmarks_dir):
    tests = {}
    benchmarks_path = benchmarks_dir / "benchmarks.json"
    if benchmarks_path.exists():
        with open(benchmarks_path, "r") as f:
            tests = json.load(f)
    return tests


def load_results(benchmarks_dir):
    results = {}
    results_path = benchmarks_dir / "benchmark_results.json"
    if results_path.exists():
        with open(results_path, "r") as f:
            results = json.load(f)
    return results


def write_result(commit, result, repo_path):
    results = load_results(repo_path)
    results[commit] = result
    with open(repo_path / "benchmark_results.json", "w") as f:
        json.dump(results, f, indent=4)


grader_prompt = dedent(
    """\
        Please grade the following diff on the following metrics:
        - correctness
        - readability
        - style
        - surprisingness
        Please reply with only a json object rating the diff from 1
        to 5 on each of those dimensions. For example:
        {"correctness": 4, "readability": 3, "style": 2, "surprisingness": 1}
        """
)


def evaluate_diff(diff: str) -> dict[str, int]:
    messages = [
        {"role": "system", "content": grader_prompt},
        {"role": "system", "content": diff},
    ]

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4-0314",
        messages=messages,
    )
    message = response.choices[0].message.content

    return json.loads(message)


async def test_edit_quality(benchmarks, max_benchmarks, evaluate_baseline, repo, refresh_repo):
    repo_path = Path(__file__).parent / f"../../benchmark_repos/{repo}"
    tests = load_tests(repo_path)
    results = load_results(repo_path)

    if len(benchmarks) > 0:
        tests_to_run = {k: v for k, v in tests.items() if k in benchmarks}
    else:
        tests_to_run = dict(islice(tests.items(), max_benchmarks))

    for test in tests_to_run.values():
        print(f"\n\n{test['name']}\n{test['prompt']}")
        if test["commit"] in results and not refresh_repo:
            print("Already ran")
            print(results[test["commit"]])
            continue

        repo_url = test["codebase_url"]
        repo_name = repo_url.split("/")[-1]
        codebase = clone_repo(repo_url, repo_name)
        os.chdir(codebase)
        with open(".git/info/exclude", "w") as f:
            f.write(
                dedent(
                    """\
                commit_information.json
                benchmarks.json
                benchmark_results.json
                transcripts*.jsonl
                gpt-output-cache.json
                """
                )
            )
        repo = Repo(".")
        start_commit = repo.commit()
        repo.git.checkout(test["commit"] + "^1")

        client = Mentat(
            paths=test["expected_features"],
        )

        await client.startup()
        await client.call_mentat_auto_accept(test["prompt"])
        await client.wait_for_edit_completion()
        await client.call_mentat("/commit")
        # I don't think this should be necessary but without it the diff isn't
        # ready in the next line.
        await client.call_mentat("q")

        diff = subprocess.check_output(["git", "show"]).decode("utf-8")
        evaluation = evaluate_diff(diff)

        print("Mentat produced the following diff:")
        print(diff)
        print("And GPT rates it in the following way:")
        print(evaluation)
        result = {
            "diff": diff,
            "grade": evaluation,
        }

        if evaluate_baseline:
            baseline = test["expected_edits"]
            evaluated_baseline = evaluate_diff(baseline)
            result["baseline"] = evaluated_baseline
            print("GPT thinks the actual diff rates:")
            print(evaluated_baseline)

        write_result(test["commit"], result, repo_path)

        # Clean up
        repo.git.reset("--hard")
        repo.git.clean("-fd")
        repo.git.checkout(start_commit)
        await client.shutdown()


if __name__ == "__main__":
    parser = common_benchmark_parser()
    args = parser.parse_args()
    asyncio.run(
        test_edit_quality(
            args.benchmarks,
            args.max_benchmarks,
            args.evaluate_baseline,
            args.repo,
            args.refresh_repo,
        )
    )
