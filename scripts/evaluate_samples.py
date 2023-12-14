from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from git import Repo  # type: ignore
from git.exc import GitCommandError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.errors import SampleError
from mentat.git_handler import get_diff_active
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import clone_repo, mentat_dir_path


def warn(msg: Any):
    print(f"\033[93m[WARNING] {msg}\033[0m")


SAMPLES_DIR = mentat_dir_path / "samples"


def find_sample_files(sample_ids: Optional[list[str]] = None) -> list[Path]:
    """Return paths to samples in SAMPLES_DIR, optionally filtered by sample_ids."""
    if sample_ids:
        sample_files = []
        for sample_id in sample_ids:
            sample_files.extend(list(SAMPLES_DIR.glob(f"*{sample_id}*.json")))
        return sample_files
    else:
        return SAMPLES_DIR.glob("*.json")


def apply_diff_to_repo(diff: str, repo: Repo, commit: bool = False) -> str | None:
    """Apply a git diff to a repo. If commit is True, commit the changes."""
    temp_id = uuid4().hex
    try:
        # Save self.diff_merge_base to a temporary .diff file
        with open(f".sample_{temp_id}.diff", "w") as f:
            f.write(diff)
        repo.git.execute(["git", "apply", f".sample_{temp_id}.diff"])
        if commit:
            repo.git.add(".")
            repo.git.commit("-m", f"sample_{temp_id}")
    except GitCommandError as e:
        return str(e)
    finally:
        os.remove(f".sample_{temp_id}.diff")


def setup_repo(sample: Sample, path_to_repo: Path | str | None = None) -> Path:
    """Clone repo, checkout merge_base, apply diff_merge_base and diff_active, return cwd."""
    if path_to_repo is None:
        cwd = clone_repo(
            url=sample.repo,
            local_dir_name=sample.repo.split("/")[-1],
            refresh=False,
        )
        if cwd is None:
            raise SampleError(f"Error cloning {sample.repo}")
    else:
        cwd = Path(path_to_repo)
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
    return cwd


async def run_mentat_on_sample(sample: Sample, cwd: Path):
    """Initialize mentat in given cwd and run the sample."""
    # Initialize Mentat PythonClient with args and messages
    paths = list[Path]()
    for a in sample.args:
        if a.startswith("--"):
            break  # TODO: Handle other mentat args?
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    conversation_history = list[ChatCompletionMessageParam]()
    sample_prompt: str | None = None
    for m in sample.messages[::-1]:
        role, content = m.get("role"), m.get("content", "")
        if role == "user":
            if sample_prompt is None:
                sample_prompt = content
            else:
                msg = ChatCompletionUserMessageParam(role="user", content=content)
                conversation_history.insert(0, msg)
        elif role == "assistant":
            if sample_prompt is None:
                warn(
                    "Ignoring assistant message after last user"
                    f" prompt,'{content[:15]}'..."
                )
            else:
                msg = ChatCompletionAssistantMessageParam(
                    role="assistant", content=content
                )
                conversation_history.insert(0, msg)
        else:
            warn(
                f"Only user and assistant messages are supported. Got {m['role']}."
                " Skipping"
            )
            continue
    if sample_prompt is None:
        raise SampleError("Sample prompt not found in messages.")
    for msg in conversation_history:
        conversation.add_message(msg)

    await python_client.call_mentat_auto_accept(sample_prompt)
    await python_client.wait_for_edit_completion()
    await python_client.shutdown()


async def evaluate_sample(sample):
    """Run a sample using Mentat and return the resulting diff"""
    cwd = setup_repo(sample)
    # TODO: Take a snapshot commit

    await run_mentat_on_sample(sample, cwd)
    diff_eval = get_diff_active() or ""
    # TODO: Subtract snapshot commit

    return diff_eval


async def main():
    parser = argparse.ArgumentParser(description="Evaluate code samples.")
    parser.add_argument("sample_ids", nargs="*", help="Optional sample IDs to evaluate")
    args = parser.parse_args()
    sample_files = find_sample_files(args.sample_ids)
    if not sample_files:
        print(f"No {'matching' if args.sample_ids else ''} sample files found.")
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
