#!/usr/bin/env python

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from textwrap import dedent

import openai
from git import Repo

from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config
from mentat.llm_api import CostTracker, count_tokens, model_context_size
from mentat.parsers.git_parser import GitParser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session_context import SESSION_CONTEXT, SessionContext
from tests.benchmarks.utils import clone_repo

system_prompt = dedent("""\
        You are part of an automated system for making synthetic data. You will be given the \
        output of `git show` for a commit. Your job is to write down what could have been a \
        user request that would lead to this commit. Focus more on the feature added or bug \
        fixed or the why of the commit than on the exact code changes. End that message with \
        END. Then write a step by step plan which if followed would lead to this commit. \
        Please respond with only those two things separated by END. Do not prepend either \
        one with additional labels such as "User Request:" or "Plan:". Don't surround either \
        with quotes or other delimiters. Don't mention mechanical details like what tools you \
        might use or the need to open files in your step by step guide. Focus on the changes \
        themselves. Number your steps 1,2,3... Put each step on its own line.""")


def ask_gpt_for_prompt_and_plan(hexsha, diff):
    # TODO: cache the cache
    if os.path.exists("gpt-output-cache.json"):
        with open("gpt-output-cache.json", "r") as f:
            cache = json.load(f)
    else:
        cache = {}

    if hexsha in cache:
        return cache[hexsha]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": diff},
    ]
    response = openai.ChatCompletion.create(
        model="gpt-4-0314",
        messages=messages,
    )

    message = response["choices"][0]["message"]["content"]
    ans = {
        "request": message.split("END")[0].strip(),
        "plan": message.split("END")[1].strip(),
    }

    cache[hexsha] = ans
    with open("gpt-output-cache.json", "w") as f:
        json.dump(cache, f)

    return ans


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
    parser = session_context.parser

    for commit in repo.iter_commits("HEAD", max_count=count):
        try:
            sha = commit.hexsha
            print("SHA:", sha)
            # Necessary for CodeContext to work
            repo.git.checkout(commit.parents[0].hexsha)
            shown = subprocess.check_output(["git", "show", sha]).decode("utf-8")
            if count_tokens(shown, "gpt-4") > 6000:
                print("Skipping because too long")
                continue

            parsedLLMResponse = GitParser().parse_string(shown)
            # There are a lot of empty commits because they are created when another
            # author merges a PR without squashing.
            if len(parsedLLMResponse.file_edits) == 0:
                continue

            code_context.set_paths(bound_files(parsedLLMResponse.file_edits), [])
            code_message = await code_context.get_code_message("", "gpt-4-0314", 0)
            prompt_and_plan = ask_gpt_for_prompt_and_plan(sha, shown)
            prompt = prompt_and_plan["request"]
            plan = prompt_and_plan["plan"]
            parsedLLMResponse.conversation = plan

            llmResponse = parser.file_edits_to_llm_message(parsedLLMResponse)
            conversation = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "system", "content": code_message},
                    {"role": "assistant", "content": llmResponse},
                ]
            }
            transcript = json.dumps(conversation)
            transcripts[sha] = transcript
            benchmark = {
                "name": commit.summary,
                "commit": sha,
                "args": {},
                "prompt": prompt,
                "expected_edits": llmResponse,
            }
            edited_files = {
                str(f.relative_to(git_root))
                for f in bound_files(parsedLLMResponse.file_edits, padding=0)
            }

            # The longest context that could have been included to generate expected_edits
            model = config.model
            mentat_prompt_tokens = count_tokens(parser.get_system_prompt(), model)
            expected_edits_tokens = count_tokens(benchmark["expected_edits"], model)
            max_context_tokens = (
                model_context_size(model) - mentat_prompt_tokens - expected_edits_tokens
            )
            # Fill-in available context
            config.auto_tokens = 1e6
            config.use_embeddings = True
            code_context.use_llm = True
            await code_context.get_code_message(
                prompt, model, max_context_tokens, benchmark["expected_edits"]
            )

            git_root_length = len(str(git_root)) + 1
            selected_features = [
                f.ref()[git_root_length:] for f in code_context.features
            ]
            selected_files = {f.split(":")[0] for f in selected_features}
            if not edited_files.issubset(selected_files):
                print(
                    "Auto-context missing required files:",
                    edited_files - selected_files,
                )
                print("Using edited_files instead")
                benchmark["expected_features"] = list(edited_files)
            else:
                benchmark["expected_features"] = list(selected_features)

            benchmarks[sha] = benchmark
        except Exception as e:
            print(e)
            continue
    return transcripts, benchmarks


class MockStream:
    def send(self, message, **kwargs):
        end = kwargs.get("end", "\n")
        print(message, end=end)


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
        default="HEAD",
        help="The commit to convert to a transcript",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="The number of commits to convert to transcripts",
    )
    args = parser.parse_args()
    clone_repo(args.repo, "for_transcripts")
    os.chdir("tests/benchmarks/repos/for_transcripts")
    old_transcripts = {}
    if os.path.exists("transcripts.jsonl"):
        with open("transcripts.jsonl", "r") as f:
            old_transcripts = json.loads(f.read())
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
        ReplacementParser(),
        code_context,
        CodeFileManager(),
        None,
    )
    SESSION_CONTEXT.set(session_context)
    repo = Repo(".")
    repo.git.checkout(args.commit)
    transcripts, benchmarks = asyncio.run(
        translate_commits_to_transcripts(repo, count=args.count)
    )
    # Everything is deterministic except for the gpt call which is cached. So transcripts
    # and benchmarks won't change run to run unless the method is changes or the cache is
    # removed.
    old_transcripts.update(transcripts)
    old_benchmarks.update(benchmarks)
    transcripts = old_transcripts
    benchmarks = old_benchmarks
    for sha, benchmark in benchmarks.items():
        benchmark["codebase_url"] = args.repo
        benchmark["codebase_name"] = args.repo.split("/")[-1]

    gpt_3_examples = []
    gpt_4_examples = []
    gpt_3_16k_examples = []
    gpt_4_32k_examples = []
    for _, transcript in transcripts.items():
        length3 = count_tokens(transcript, "gpt-3.5-turbo-0613")
        length4 = count_tokens(transcript, "gpt-4-0613")
        padding = 100  # Our count_tokens method isn't exactly right because chat annotations take tokens.
        if length3 < 4097 - padding:
            gpt_3_examples.append(transcript)
        if length4 < 8192 - padding:
            gpt_4_examples.append(transcript)
        if length3 < 16385 - padding:
            gpt_3_16k_examples.append(transcript)
        if length4 < 32768 - padding:
            gpt_4_32k_examples.append(transcript)

    with open("transcripts.jsonl", "w") as f:
        json.dump(transcripts, f)
    with open("transcripts_gpt3.jsonl", "w") as f:
        f.write("\n".join(gpt_3_examples))
    with open("transcripts_gpt4.jsonl", "w") as f:
        f.write("\n".join(gpt_4_examples))
    with open("transcripts_gpt3_16k.jsonl", "w") as f:
        f.write("\n".join(gpt_3_16k_examples))
    with open("transcripts_gpt4_32k.jsonl", "w") as f:
        f.write("\n".join(gpt_4_32k_examples))
    with open("benchmarks.json", "w") as f:
        json.dump(benchmarks, f)
    repo.git.checkout(args.commit)
