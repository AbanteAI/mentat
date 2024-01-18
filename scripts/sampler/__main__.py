from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

from add_context import add_context
from finetune import generate_finetune
from remove_context import remove_context
from validate import validate_sample

from mentat.llm_api_handler import count_tokens, prompt_tokens
from mentat.sampler.sample import Sample
from mentat.utils import mentat_dir_path

# benchmarks is not automatically included in path
benchamrks_dir_path = Path(__file__).resolve().parent.parent.parent / "benchmarks"
if str(benchamrks_dir_path) not in sys.path:
    sys.path.insert(0, str(benchamrks_dir_path))
from benchmarks.benchmark_runner import (  # noqa: E402
    compare_diffs,
    grade_diff_syntax,
    grade_model_response,
)
from benchmarks.run_sample import run_sample  # noqa: E402


def warn(msg: Any):
    print(f"\033[93m[WARNING] {msg}\033[0m")


SAMPLES_DIR = mentat_dir_path / "samples"
os.makedirs(SAMPLES_DIR, exist_ok=True)


async def main():
    parser = argparse.ArgumentParser(description="Evaluate code samples.")
    parser.add_argument("sample_ids", nargs="*", help="Optional sample IDs to run")
    parser.add_argument(
        "--number", "-n", type=int, default=None, help="Maximum number of times to run"
    )
    parser.add_argument(
        "--validate",
        "-v",
        action="store_true",
        help="Validate samples conform to spec",
    )
    parser.add_argument(
        "--finetune", "-f", action="store_true", help="Generate fine-tuning examples"
    )
    parser.add_argument(
        "--add-context", "-a", action="store_true", help="Add extra context to samples"
    )
    parser.add_argument(
        "--remove-context",
        "-r",
        action="store_true",
        help="Remove context from samples",
    )
    args = parser.parse_args()
    sample_files = []
    if args.sample_ids:
        for sample_id in args.sample_ids:
            sample_files.extend(list(SAMPLES_DIR.glob(f"*{sample_id}*.json")))
    else:
        sample_files = list(SAMPLES_DIR.glob("*.json"))
    if not sample_files:
        print(f"No {'matching ' if args.sample_ids else ''}sample files found.")
        return

    random.shuffle(sample_files)
    logs = []
    for sample_file in sample_files:
        if args.number and len(logs) >= args.number:
            break
        if not sample_file.exists():
            warn(f"Sample file {sample_file} does not exist.")
            continue
        try:
            sample = Sample.load(sample_file)
        except Exception as e:
            warn(f"Error loading sample {sample_file}: {e}")
            continue
        if (args.add_context or args.remove_context) and (
            "[ADDED CONTEXT]" in sample.title or "[REMOVED CONTEXT]" in sample.title
        ):
            warn(f"Skipping {sample.id[:8]}: has already been modified.")
            continue
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
            try:
                example = await generate_finetune(sample)
                # Toktoken only includes encoding for openAI models, so this isn't always correct
                if "messages" in example:
                    tokens = prompt_tokens(example["messages"], "gpt-4")
                elif "text" in example:
                    tokens = count_tokens(example["text"], "gpt-4", full_message=False)
                example["tokens"] = tokens
                print(
                    "Generated finetune example"
                    f" {sample.id[:8]} ({example['tokens']} tokens)"
                )
                logs.append(example)
            except Exception as e:
                warn(
                    f"Error generating finetune example for sample {sample.id[:8]}: {e}"
                )
        elif args.add_context:
            try:
                new_sample = await add_context(sample)
                sample_file = SAMPLES_DIR / f"sample_{new_sample.id}.json"
                new_sample.save(sample_file)
                print(f"Generated new sample with extra context: {sample_file}")
                logs.append({"id": new_sample.id, "prototype_id": sample.id})
            except Exception as e:
                warn(f"Error adding extra context to sample {sample.id[:8]}: {e}")
        elif args.remove_context:
            if not sample.context or len(sample.context) == 1:
                warn(f"Skipping {sample.id[:8]}: no context to remove.")
                continue
            try:
                new_sample = await remove_context(sample)
                new_sample.save(SAMPLES_DIR / f"sample_{new_sample.id}.json")
                print(f"Generated new sample with context removed: {sample_file}")
                logs.append({"id": new_sample.id, "prototype_id": sample.id})
            except Exception as e:
                warn(f"Error removing context from sample {sample.id[:8]}: {e}")
        else:
            print(f"Running sample {sample.id[:8]}")
            print(f"  Prompt: {sample.message_prompt}")
            sample_result = await run_sample(sample)
            message_eval = sample_result["message_eval"]
            diff_eval = sample_result["diff_eval"]

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
        # Dump all logs into a .jsonl file
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = mentat_dir_path / f"finetune_examples_{timestamp}.jsonl"
        tokens = 0
        with open(fname, "w") as f:
            for log in logs:
                tokens += log["tokens"]
                del log["tokens"]
                f.write(json.dumps(log) + "\n")
        print(f"{len(logs)} fine-tuning examples ({tokens} tokens) saved to {fname}.")
    elif args.add_context:
        print(f"{len(logs)} samples with extra context generated.")
    elif args.remove_context:
        print(f"{len(logs)} samples with context removed generated.")


if __name__ == "__main__":
    asyncio.run(main())
