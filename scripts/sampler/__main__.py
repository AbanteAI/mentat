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

from finetune import generate_finetune
from validate import validate_sample

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
    parser.add_argument("--number", "-n", type=int, default=None, help="Maximum number of times to run")
    parser.add_argument(
        "--validate",
        "-v",
        action="store_true",
        help="Validate samples conform to spec",
    )
    parser.add_argument("--finetune", "-f", action="store_true", help="Generate fine-tuning examples")
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
        if args.validate:
            is_valid, reason = await validate_sample(sample)
            status = "\033[92mPASSED\033[0m" if is_valid else f"\033[91mFAILED: {reason}\033[0m"
            print(f"[{sample.id[:8]}] {sample.title}: {status}")
            logs.append({"id": sample.id, "is_valid": is_valid, "reason": reason})
        elif args.finetune:
            try:
                example = await generate_finetune(sample)
                spice = Spice()
                if "messages" in example:
                    tokens = spice.count_prompt_tokens(example["messages"], "gpt-4")
                elif "text" in example:
                    tokens = spice.count_tokens(example["text"], "gpt-4", is_message=False)
                example["tokens"] = tokens
                print("Generated finetune example" f" {sample.id[:8]} ({example['tokens']} tokens)")
                logs.append(example)
            except Exception as e:
                warn(f"Error generating finetune example for sample {sample.id[:8]}: {e}")
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
        print(f"{sum([log['is_valid'] for log in logs])}/{len(logs)} samples passed validation.")
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


if __name__ == "__main__":
    asyncio.run(main())
