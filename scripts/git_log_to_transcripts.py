#!/usr/bin/env python

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock

import openai
from git import Repo

from mentat.code_context import CodeContext, CodeContextSettings
from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.llm_api import count_tokens
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
        with quotes or other delimiters.""")


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
        if len(file_edit.replacements) == 0:
            min_line = 10000
            max_line = 0
            for replacement in file_edit.replacements:
                min_line = min(min_line, replacement.starting_line)
                max_line = max(max_line, replacement.ending_line)
            files.append(
                Path(
                    "%s:%d-%d"
                    % (file_edit.file_path, min_line - padding, max_line + padding)
                )
            )
        else:
            files.append(file_edit.file_path)
    return files


async def translate_commits_to_transcripts(repo, count=10, skip=[]):
    transcripts = {}

    for commit in repo.iter_commits("HEAD", max_count=count):
        try:
            sha = commit.hexsha
            print("SHA:", sha)
            if sha in skip:
                continue
            shown = subprocess.check_output(["git", "show", sha]).decode("utf-8")
            if count_tokens(shown, "gpt-4") > 6000:
                print("Skipping because too long")
                continue

            # Necessary for CodeContext to work
            repo.git.checkout(commit.parents[0].hexsha)

            parsedLLMResponse = GitParser().parse_string(shown)

            SESSION_CONTEXT.get().code_context.set_paths(
                bound_files(parsedLLMResponse.file_edits), []
            )

            code_message = await code_context.get_code_message("", "gpt-4-0314", 0)
            prompt_and_plan = ask_gpt_for_prompt_and_plan(sha, shown)
            parsedLLMResponse.conversation = prompt_and_plan["plan"]

            llmResponse = ReplacementParser().file_edits_to_llm_message(
                parsedLLMResponse
            )
            conversation = {
                "messages": [
                    {"role": "user", "content": prompt_and_plan["request"]},
                    {"role": "system", "content": code_message},
                    {"role": "assistant", "content": llmResponse},
                ]
            }
            transcript = json.dumps(conversation)
            transcripts[sha] = transcript
        except Exception as e:
            print(e)
            continue
    return transcripts


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
    skip = []
    old_transcripts = {}
    if os.path.exists("transcripts.jsonl"):
        with open("transcripts.jsonl", "r") as f:
            old_transcripts = json.loads(f.read())
        skip = list(old_transcripts.keys())

    stream = AsyncMock()
    config = ConfigManager(os.getcwd(), stream)
    code_context_settings = CodeContextSettings(False, False, False, False, 0)
    code_context = CodeContext(stream, os.getcwd(), code_context_settings)
    session_context = SessionContext(
        stream,
        None,
        os.getcwd(),
        config,
        ReplacementParser(),
        code_context,
        CodeFileManager(),
        None,
    )
    SESSION_CONTEXT.set(session_context)
    repo = Repo(".")
    repo.git.checkout(args.commit)
    transcripts = asyncio.run(
        translate_commits_to_transcripts(repo, count=args.count, skip=skip)
    )
    gpt_3_examples = []
    gpt_4_examples = []
    for _, transcript in transcripts.items():
        length3 = count_tokens(transcript, "gpt-3.5-turbo-0613")
        length4 = count_tokens(transcript, "gpt-4-0613")
        if length3 < 4097:
            gpt_3_examples.append(transcript)
        if length4 < 8192:
            gpt_4_examples.append(transcript)

    transcripts.update(old_transcripts)
    with open("transcripts.jsonl", "w") as f:
        json.dump(transcripts, f)
    with open("transcripts_gpt3.jsonl", "a") as f:
        for transcript in gpt_3_examples:
            f.write(transcript + "\n")
    with open("transcripts_gpt4.jsonl", "a") as f:
        for transcript in gpt_4_examples:
            f.write(transcript + "\n")
