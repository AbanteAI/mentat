#!/usr/bin/env python

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from textwrap import dedent

from git import Repo
from openai import OpenAI

from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config
from mentat.llm_api import CostTracker, count_tokens
from mentat.parsers.git_parser import GitParser
from mentat.session_context import SESSION_CONTEXT, SessionContext
from tests.benchmarks.context_benchmark import MockStream, select_features_for_benchmark
from tests.benchmarks.utils import clone_repo

system_prompt = dedent("""\
        You are part of an automated system for making synthetic data. You will be given the \
        output of `git show` for a commit. Please respond only in json. The json should have \
        the following entries:
        - request (type string): a user request that would lead to this commit. Focus more on \
        the feature added or bug fixed or the why of the commit than on the exact code changes.
        - plan (type string): a step by step plan which if followed would lead to this commit. \
        Your plan should be numbered 1,2,3... with each step separated by a newline. Don't \
        mention mechanical details like what tools you might use or the need to open files. \
        Focus on the sequence of changes necessary.
        - documentation (type boolean): True if this change is mostly or entirely changes to \
        the documentation.
        - configuration (type boolean): True if this change only affects configuration. For \
        example deploy scripts, dependency versioning, or linting/compiler options.
        - bug (type boolean): True if this change is a bug fix.
        - feature (type boolean): True if this change is a new feature.
        - complexity (type int): On a scale of 1 to 10 rate how interesting you think this \
        change is. Use your judgement.
        """)

commit_information = "commit_information.json"


def gpt_commit_summary(hexsha, diff):
    # TODO: cache the cache
    if os.path.exists(commit_information):
        with open(commit_information, "r") as f:
            cache = json.load(f)
    else:
        cache = {}

    if hexsha in cache:
        return cache[hexsha]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": diff},
    ]
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4-0314",
        messages=messages,
    )
    message = response.choices[0].message.content

    ans = json.loads(message)

    cache[hexsha] = ans
    with open(commit_information, "w") as f:
        json.dump(cache, f)

    return ans


def update_cache(hexsha, value):
    with open(commit_information, "r") as f:
        cache = json.load(f)
        cache[hexsha] = value
    with open(commit_information, "w") as f:
        json.dump(cache, f)


def bound_files(file_edits, padding=5):
    files = []
    for file_edit in file_edits:
        if file_edit.is_creation:
            continue
        if len(file_edit.replacements) != 0:
            min_line = 10000
            max_line = 1
            for replacement in file_edit.replacements:
                min_line = min(min_line, replacement.starting_line)
                max_line = max(max_line, replacement.ending_line)
            files.append(
                Path(
                    "%s:%d-%d"
                    % (
                        file_edit.file_path,
                        max(1, min_line - padding),
                        max_line + padding,
                    )
                )
            )
        else:
            files.append(file_edit.file_path)
    return files


async def translate_commits_to_transcripts(repo, count=10):
    transcripts = {}
    benchmarks = {}
    session_context = SESSION_CONTEXT.get()
    code_context = session_context.code_context
    config = session_context.config
    git_root = session_context.git_root
    parser = config.parser

    for commit in repo.iter_commits("HEAD", max_count=count):
        try:
            sha = commit.hexsha
            print("SHA:", sha)
            # Necessary for CodeContext to work
            repo.git.checkout(commit.parents[0].hexsha)
            shown = subprocess.check_output(
                ["git", "show", sha, "-m", "--first-parent"]
            ).decode("utf-8")
            if count_tokens(shown, "gpt-4") > 6000:
                print("Skipping because too long")
                continue

            parsedLLMResponse = GitParser().parse_string(shown)

            code_context.set_paths(bound_files(parsedLLMResponse.file_edits), [])
            code_message = await code_context.get_code_message("", 0)
            commit_summary = gpt_commit_summary(sha, shown)
            prompt = commit_summary["request"]
            plan = commit_summary["plan"]
            parsedLLMResponse.conversation = plan

            llmResponse = parser.file_edits_to_llm_message(parsedLLMResponse)
            conversation = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "system", "content": code_message},
                    {"role": "assistant", "content": llmResponse},
                ]
            }
            commit_summary["mocked_conversation"] = conversation

            update_cache(sha, commit_summary)

            transcript = json.dumps(conversation)
            transcripts[sha] = transcript
            benchmark = {
                "name": commit.summary,
                "commit": sha,
                "args": {},
                "prompt": prompt,
                "expected_edits": llmResponse,
                "edited_features": list(
                    {
                        str(f.relative_to(git_root))
                        for f in bound_files(parsedLLMResponse.file_edits, padding=0)
                    }
                ),
                "selected_features": [],
            }
            try:
                result = await select_features_for_benchmark(
                    session_context,
                    benchmark,
                    eval=False,
                    use_expected=True,
                    use_llm=True,
                )
                benchmark["selected_features"] = result["features"]
            except Exception as e:
                print(f"Failed to select features: {e}")

            benchmarks[sha] = benchmark
        except Exception as e:
            # You may see "this is a directory" errors. This is caused by git commits
            # to sub projects which we don't want to process anyway.
            print(e)
            continue
    return transcripts, benchmarks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert git commits into transcripts")
    parser.add_argument(
        "--repo",
        type=str,
        default="http://github.com/AbanteAI/mentat",
        help="The repo to convert to transcripts",
    )
    parser.add_argument(
        "--commit",
        type=str,
        default="main",
        help="The commit to convert to a transcript",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="The number of commits to convert to transcripts",
    )
    args = parser.parse_args()
    repo_name = args.repo.split("/")[-1]
    clone_repo(args.repo, repo_name, depth=args.count)
    os.chdir(f"tests/benchmarks/repos/{repo_name}")
    old_benchmarks = {}
    if os.path.exists("benchmarks.json"):
        with open("benchmarks.json", "r") as f:
            old_benchmarks = json.loads(f.read())

    stream = MockStream()
    config = Config()
    code_context = CodeContext(stream, os.getcwd())
    session_context = SessionContext(
        stream,
        CostTracker(),
        Path.cwd(),
        config,
        code_context,
        CodeFileManager(),
        None,
    )
    SESSION_CONTEXT.set(session_context)
    repo = Repo(".")
    repo.git.checkout(args.commit)
    _, benchmarks = asyncio.run(
        translate_commits_to_transcripts(repo, count=args.count)
    )
    old_benchmarks.update(benchmarks)
    benchmarks = old_benchmarks
    for sha, benchmark in benchmarks.items():
        benchmark["codebase_url"] = args.repo
        benchmark["codebase_name"] = args.repo.split("/")[-1]

    with open("benchmarks.json", "w") as f:
        json.dump(benchmarks, f)
    repo.git.checkout(args.commit)
