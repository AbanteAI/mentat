from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from pathlib import Path
from textwrap import dedent
from typing import Any
from uuid import uuid4

import attr
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.code_feature import (
    CodeFeature,
    get_code_message_from_features,
    get_consolidated_feature_refs,
)
from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.parsers.git_parser import GitParser
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import (
    apply_diff_to_repo,
    get_active_snapshot_commit,
    setup_repo,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path
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


async def evaluate_sample(sample, cwd: Path | str | None = None):
    """Run a sample using Mentat and return the resulting diff"""

    repo = setup_repo(
        url=sample.repo,
        cwd=cwd,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)

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
        if not sample.message_edit and not sample.diff_edit:
            return False, "Samples must include either diff_edit or message_edit."

        try:
            repo = setup_repo(
                url=sample.repo,
                cwd=cwd,
                commit=sample.merge_base,
                diff_merge_base=sample.diff_merge_base,
                diff_active=sample.diff_active,
            )
        except SampleError as e:
            return False, str(e)
        # TODO: Validate context (paths)
        if sample.diff_edit:
            errors = apply_diff_to_repo(sample.diff_edit, repo)
            if errors:
                return False, f"Error applying diff_edit: {errors}"

        return True, ""
    except Exception as e:
        return False, f"Error validating sample: {e}"


async def add_extra_context(sample, extra_tokens: int = 5000) -> Sample:
    """Return a duplicate sample with extra (auto-context generated) context."""
    # Setup mentat CodeContext with included_files
    repo = setup_repo(
        url=sample.repo,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()

    # Use auto-context to add extra tokens, then copy the resulting features
    ctx = SESSION_CONTEXT.get()
    ctx.config.auto_context_tokens = extra_tokens
    _ = await ctx.code_context.get_code_message(
        prompt_tokens=0, prompt=sample.message_prompt
    )
    included_features = list(
        f for fs in ctx.code_context.include_files.values() for f in fs
    )
    auto_features = ctx.code_context.auto_features
    all_features = get_consolidated_feature_refs(included_features + auto_features)
    await python_client.shutdown()

    new_sample = Sample(**attr.asdict(sample))
    new_sample.context = [str(f) for f in all_features]
    new_sample.id = uuid4().hex
    new_sample.title = f"{sample.title} [ADD {extra_tokens} CONTEXT]"
    return new_sample


async def remove_context(sample) -> Sample:
    """Return a duplicate sample with one context item removed and a warning message"""

    # Setup the repo and load context files
    repo = setup_repo(
        url=sample.repo,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)
    python_client = PythonClient(cwd=Path("."), paths=[])
    await python_client.startup()

    context = [CodeFeature(cwd / p) for p in sample.context]
    i_target = random.randint(0, len(context) - 1)
    background_features = context[:i_target] + context[i_target + 1 :]
    target_features = [context[i_target]]
    background_context = "\n".join(get_code_message_from_features(background_features))
    target_context = "\n".join(get_code_message_from_features(target_features))

    # Build conversation: [rejection_prompt, message_prompt, keep_context, remove_context]
    messages = [
        ChatCompletionSystemMessageParam(
            role="system",
            content=dedent("""\
                You are part of an LLM Coding Assistant, designed to answer questions and
                complete tasks for developers. Specifically, you generate examples of
                interactions where the user has not provided enough context to fulfill the
                query. You will be shown an example query, some background code which will
                be included, and some target code which is NOT be included.

                Pretend you haven't seen the target code, and tell the user what additional
                information you'll need in order to fulfill the task. Take a deep breath,
                focus, and then complete your task by following this procedure:

                1. Read the USER QUERY (below) carefully. Consider the steps involved in
                   completing it.
                2. Read the BACKROUND CONTEXT (below that) carefully. Consider how it
                   contributes to completing the task.
                3. Read the TARGET CONTEXT (below that) carefully. Consider how it
                   contributes to completing the task.
                4. Think of a short (1-sentence) explanation of why the TARGET CONTEXT is
                   required to complete the task.
                5. Return a ~1 paragraph message to the user explaining why the BACKGROUND
                   CONTEXT is not sufficient to answer the question.

                REMEMBER:
                * Don't reference TARGET CONTEXT specifically. Answer as if you've never
                  seen it, you just know you're missing something essential.
                * Return #5 (your response to the user) as a single paragraph, without
                  preamble, notes, extra spacing or additional commentary.
            """),
        ),
        ChatCompletionUserMessageParam(
            role="user", content=f"USER QUERY: {sample.message_prompt}"
        ),
        ChatCompletionSystemMessageParam(
            role="system",
            content=f"BACKGROUND CONTEXT: {background_context}",
        ),
        ChatCompletionSystemMessageParam(
            role="system",
            content=f"TARGET CONTEXT: {target_context}",
        ),
    ]

    # Ask gpt-4 to generate rejection prompt
    llm_api_handler = python_client.session.ctx.llm_api_handler
    llm_api_handler.initialize_client()
    llm_response = await llm_api_handler.call_llm_api(
        messages=messages,
        model=python_client.session.ctx.config.model,
        stream=False,
    )
    message = (llm_response.choices[0].message.content) or ""

    # Ask user to review and accept/reject
    print("Sample Prompt:", sample.message_prompt)
    print("Removed context:", target_context)
    print("Generated reason:", message)
    print("Press ENTER to accept, or type a new reason to reject.")
    response = input()
    if response:
        message = response
    if not message:
        raise SampleError("No rejection reason provided. Aborting.")

    # Create and return a duplicate/udpated sample
    new_sample = Sample(**attr.asdict(sample))
    new_sample.context = [str(f) for f in background_context]
    new_sample.id = uuid4().hex
    new_sample.title = f"{sample.title} [REMOVE {target_context}]"
    new_sample.message_edit = message
    new_sample.diff_edit = None

    return new_sample


async def generate_finetune_gpt(sample, cwd: Path | str | None = None):
    """Generate a fine-tuning example from the sample for GPT-3.5

    {"messages": [{"role": "user", "content": "Hello, world!"}, ...]}
    """
    repo = setup_repo(
        url=sample.repo,
        cwd=cwd,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)

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
        message_example += ctx.config.parser.file_edits_to_llm_message(
            parsed_llm_response
        )
    conversation.append({"role": "system", "content": message_example})

    await python_client.shutdown()
    return {"messages": conversation}


async def main():
    parser = argparse.ArgumentParser(description="Evaluate code samples.")
    parser.add_argument("sample_ids", nargs="*", help="Optional sample IDs to evaluate")
    parser.add_argument(
        "--validate", action="store_true", help="Validate samples instead of evaluating"
    )
    parser.add_argument(
        "--finetune", action="store_true", help="Generate fine-tuning examples"
    )
    parser.add_argument(
        "--extra-context", action="store_true", help="Add extra context to samples"
    )
    parser.add_argument(
        "--remove-context", action="store_true", help="Remove context from samples"
    )
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
            status = (
                "\033[92mPASSED\033[0m"
                if is_valid
                else f"\033[91mFAILED: {reason}\033[0m"
            )
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
                warn(
                    f"Error generating fine-tuning example for sample {sample.id}: {e}"
                )
        elif args.extra_context:
            print(f"Adding extra context to sample {sample.id[:8]}")
            try:
                new_sample = await add_extra_context(sample)
                new_sample.save(SAMPLES_DIR / f"sample_{new_sample.id}.json")
                logs.append({"id": new_sample.id, "prototype_id": sample.id})
            except Exception as e:
                warn(f"Error adding extra context to sample {sample.id}: {e}")
        elif args.remove_context:
            print(f"Removing context from sample {sample.id[:8]}")
            try:
                new_sample = await remove_context(sample)
                new_sample.save(SAMPLES_DIR / f"sample_{new_sample.id}.json")
                logs.append({"id": new_sample.id, "prototype_id": sample.id})
            except Exception as e:
                warn(f"Error removing context from sample {sample.id}: {e}")
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
            logs.append(
                {
                    "id": sample.id,
                    "title": sample.title,
                    "prompt": sample.message_prompt,
                    "diff_grade": diff_grade,
                    "response_grade": response_grade,
                    "comparison_grade": comparison_grade,
                }
            )

    if args.validate:
        print(
            f"{sum([log['is_valid'] for log in logs])}/{len(logs)} samples passed"
            " validation."
        )
    elif args.finetune:
        print(f"{len(logs)} fine-tuning examples generated.")
    elif args.extra_context:
        print(f"{len(logs)} samples with extra context generated.")
    elif args.remove_context:
        print(f"{len(logs)} samples with context removed generated.")


if __name__ == "__main__":
    asyncio.run(main())
