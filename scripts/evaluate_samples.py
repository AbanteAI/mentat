from __future__ import annotations

import argparse
import asyncio
import os
import json
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
from mentat.parsers.git_parser import GitParser
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import get_active_snapshot_commit
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import clone_repo, mentat_dir_path
from tests.benchmarks.benchmark_runner import (
    compare_diffs,
    grade_diff_syntax,
    grade_model_response,
)


def warn(msg: Any):
    print(f"\033[93m[WARNING] {msg}\033[0m")


SAMPLES_DIR = mentat_dir_path / "samples"
os.makedirs(SAMPLES_DIR, exist_ok=True)
FINETUNE_DIR = mentat_dir_path / "finetune"
os.makedirs(FINETUNE_DIR, exist_ok=True)



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
    await python_client.shutdown()

    # Get the diff between pre- and post-edit
    diff_eval = get_git_diff(commit_active or "HEAD", cwd=cwd)

    return diff_eval


async def validate_sample(sample, cwd: Path | str | None = None) -> tuple[bool, str]:
    """Validate a sample by applying diffs and checking sample fields."""
    try:
        required_fields = ["id", "repo", "merge_base", "message_prompt"]
        for field in required_fields:
            if not getattr(sample, field):
                return False, f"Missing required field: {field}"
        if (not sample.message_edit and not sample.diff_edit):
            return False, "Samples must include either diff_edit or message_edit."
        
        # Setup repo
        if cwd is None:
            cwd = clone_repo(
                url=sample.repo,
                local_dir_name=sample.repo.split("/")[-1],
                refresh=False,
            )
            if cwd is None:
                return False, f"Error cloning repo: {sample.repo}"
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
                return False, f"Error applying diff_merge_base: {errors}"
        if sample.diff_active:
            errors = apply_diff_to_repo(sample.diff_active, repo)
            if errors:
                return False, f"Error applying diff_active: {errors}"
        # TODO: Validate context (paths)
        if sample.diff_edit:
            errors = apply_diff_to_repo(sample.diff_edit, repo)
            if errors:
                return False, f"Error applying diff_edit: {errors}"
        
        return True, ""
    except Exception as e:
        return False, f"Error validating sample: {e}"
    

async def generate_finetune_gpt(sample, cwd: Path | str | None = None):
    """Generate a fine-tuning example from the sample for GPT-3.5
    
    {"messages": [{"role": "user", "content": "Hello, world!"}, ...]}
    """
    # Setup repo, including diff_merge_base and diff_active
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

    # Run sample in PythonClient
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()
    ctx = SESSION_CONTEXT.get()
    
    # Build the conversation
    conversation = list[dict[str, str]]()
    if paths:
        code_message = await ctx.code_context.get_code_message(0)
        conversation.append({"role": "system", "content": code_message})
    # TODO: Ignore conversation_history for now because file_edits are not yet included
    # conversation += sample.message_history[::-1]
    conversation.append({"role": "user", "content": sample.message_prompt})
    message_example = sample.message_edit or ""
    if sample.diff_edit:  # Convert any diff_edit to block format for answer
        parsed_llm_response = GitParser().parse_string(sample.diff_edit)
        message_example += ctx.config.parser.file_edits_to_llm_message(parsed_llm_response)
    conversation.append({"role": "system", "content": message_example})
    
    await python_client.shutdown()
    return {"messages": conversation}


async def main():
    parser = argparse.ArgumentParser(description="Evaluate code samples.")
    parser.add_argument("sample_ids", nargs="*", help="Optional sample IDs to evaluate")
    parser.add_argument("--validate", action="store_true", help="Validate samples instead of evaluating")
    parser.add_argument("--finetune", action="store_true", help="Generate fine-tuning examples")
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
    
    logs = []
    for sample_file in sample_files:
        if not sample_file.exists():
            warn(f"Sample file {sample_file} does not exist.")
            continue
        sample = Sample.load(sample_file)
        if args.validate:
            is_valid, reason = await validate_sample(sample)
            status = "\033[92mPASSED\033[0m" if is_valid else f"\033[91mFAILED: {reason}\033[0m"
            print(f"[{sample.id[:8]}] {sample.title}: {status}")
            logs.append({"id": sample.id, "is_valid": is_valid, "reason": reason})
        elif args.finetune:
            print(f"Generating fine-tuning example for sample {sample.id[:8]}")
            try:
                example = await generate_finetune_gpt(sample)
                example_file = FINETUNE_DIR / f"finetune_{sample.id}.json"
                with open(example_file, "w") as f:
                    json.dump(example, f, indent=4)
                logs.append({"id": sample.id, "example_file": example_file})
            except Exception as e:
                warn(f"Error generating fine-tuning example for sample {sample.id}: {e}")
        else:
            print(f"Evaluating sample {sample.id[:8]}")
            print(f"  Prompt: {sample.message_prompt}")
            diff_eval = await evaluate_sample(sample)
            message_eval = ""  # TODO: return from evaluate_sample

            diff_grade = await grade_diff_syntax(diff_eval)
            print(f"  Diff Grade: {diff_grade}")
            response_grade = await grade_model_response(message_eval + "\n" + diff_eval)
            print(f"  Response Grade: {response_grade}")
            comparison_grade = await compare_diffs(sample.diff_edit, diff_eval)
            print(f"  Comparison Grade: {comparison_grade}")
            logs.append({
                "id": sample.id,
                "title": sample.title,
                "prompt": sample.message_prompt,
                "diff_grade": diff_grade,
                "response_grade": response_grade,
                "comparison_grade": comparison_grade,
            })
    
    if args.validate:
        print(f"{sum([log['is_valid'] for log in logs])}/{len(logs)} samples passed validation.")
    elif args.finetune:
        print(f"{len(logs)} fine-tuning examples generated.")


if __name__ == "__main__":
    asyncio.run(main())
