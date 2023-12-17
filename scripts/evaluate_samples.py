from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from git import Repo  # type: ignore
from git.exc import GitCommandError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import get_active_snapshot_commit
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import clone_repo, mentat_dir_path


def warn(msg: Any):
    print(f"\033[93m[WARNING] {msg}\033[0m")


SAMPLES_DIR = mentat_dir_path / "samples"


def apply_diff_to_repo(diff: str, repo: Repo, commit: bool = False) -> str | None:
    """Apply a git diff to a repo. If commit is True, commit the changes."""
    temp_id = uuid4().hex
    try:
        # Save self.diff_merge_base to a temporary .diff file
        with open(f".sample_{temp_id}.diff", "w") as f:
            f.write(diff)
        repo.git.execute(["git", "apply", f".sample_{temp_id}.diff"])
        os.remove(f".sample_{temp_id}.diff")
        if commit:
            repo.git.add(".")
            repo.git.commit("-m", f"sample_{temp_id}")
    except GitCommandError as e:
        try:
            os.remove(f".sample_{temp_id}.diff")
        except FileNotFoundError:
            pass
        return str(e)


async def evaluate_sample(sample, cwd: Path | str | None = None):
    """Run a sample using Mentat and return the resulting diff"""

    # Setup repo
    if cwd is None:
        cwd = clone_repo(
            url=sample.repo,
            local_dir_name=sample.repo.split("/")[-1],
            refresh=False,
        )
        if cwd is None:
            raise SampleError(f"Error cloning {sample.repo}")
    else:
        cwd = Path(cwd)
    os.chdir(cwd)
    repo = Repo(".")
    repo.head.reset(index=True, working_tree=True)  # reset tracked files
    repo.git.execute(["git", "clean", "-fd"])  # remove untracked files/directories
    repo.git.fetch("--all")
    repo.git.checkout(sample.merge_base)
    if sample.diff_merge_base:
        errors = apply_diff_to_repo(sample.diff_merge_base, repo, commit=True)
        if errors:
            raise SampleError(f"Error applying diff_merge_base: {errors}")
    if sample.diff_active:
        errors = apply_diff_to_repo(sample.diff_active, repo)
        if errors:
            raise SampleError(f"Error applying diff_active: {errors}")

    # Make a commit from the pre-edited state (should match diff_active)
    commit_active = get_active_snapshot_commit(repo)

    # Run sample in PythonClient
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    for msg in sample.message_history:
        msg_cls = {
            "user": ChatCompletionUserMessageParam,
            "assistant": ChatCompletionAssistantMessageParam,
        }.get(msg["role"])
        if msg_cls is None:
            raise SampleError(f"Invalid role found in message_history: {msg['role']}")
        conversation.add_message(msg_cls(role=msg["role"], content=msg["content"]))
    await python_client.call_mentat_auto_accept(sample.message_prompt)
    await python_client.wait_for_edit_completion()
    await python_client.shutdown()

    # Get the diff between pre- and post-edit
    diff_eval = get_git_diff(commit_active or "HEAD", cwd=cwd)

    return diff_eval


async def main():
    parser = argparse.ArgumentParser(description="Evaluate code samples.")
    parser.add_argument("sample_ids", nargs="*", help="Optional sample IDs to evaluate")
    args = parser.parse_args()
    sample_files = []
    if args.sample_ids:
        for sample_id in args.sample_ids:
            sample_files.extend(list(SAMPLES_DIR.glob(f"*{sample_id}*.json")))
    else:
        sample_files = SAMPLES_DIR.glob("*.json")
    if not sample_files:
        print(f"No {'matching ' if args.sample_ids else ''}sample files found.")
        return

    for sample_file in sample_files:
        if sample_file.exists():
            sample = Sample.load(sample_file)
            results = await evaluate_sample(sample)
            print(f"Results for {sample_file.stem}: {json.dumps(results, indent=4)}")
        else:
            print(f"Sample file {sample_file} does not exist.")


if __name__ == "__main__":
    asyncio.run(main())
