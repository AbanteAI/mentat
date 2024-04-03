import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmarks.arg_parser import common_benchmark_parser
from benchmarks.run_sample import setup_sample
from benchmarks.swe_bench_runner import SWE_BENCH_SAMPLES_DIR, get_swe_samples
from mentat import Mentat
from mentat.config import Config
from mentat.sampler.sample import Sample
from mentat.session_context import SESSION_CONTEXT


def _score(predicted: set[Path], expected: set[Path]) -> dict[str, Any]:
    true_positives = predicted.intersection(expected)
    false_positives = predicted.difference(expected)
    false_negatives = expected.difference(predicted)
    precision = len(true_positives) / (len(true_positives) + len(false_positives))
    recall = len(true_positives) / (len(true_positives) + len(false_negatives))
    return {"precision": precision, "recall": recall, "n_true": len(expected)}


async def run_auto_context_benchmark(
    sample: Sample, config: Config, cwd: Path | str | None = None, include_context: bool = False
) -> dict[str, Any]:
    """Run a sample using Mentat and return the resulting diff"""
    starting_dir = Path.cwd()

    if not config.auto_context_tokens or not sample.context:
        raise ValueError(
            "In order to run the auto-context benchmark, sample.context must not "
            "be empty (ground truth) and config.auto_context_tokens must be > 0."
        )
    paths = [] if not include_context else [Path(a) for a in sample.context]

    try:
        _, cwd, _, _ = setup_sample(sample, None, skip_test_exec=True)
        exclude_paths = [cwd / ".venv"]
        mentat = Mentat(cwd=cwd, paths=paths, exclude_paths=exclude_paths, config=config or Config())
        await mentat.startup()
        await asyncio.sleep(0.01)  # Required to initialize llm_api_handler for embeddings

        # TODO: If there's a conversation history, we might consider the cumulative context.
        # Setup a mock for the LLM response and run the conversation until this point.
        code_context = SESSION_CONTEXT.get().code_context
        _ = await code_context.get_code_message(0, sample.message_prompt)
        predicted = set(path.relative_to(cwd) for path in code_context.include_files.keys())
        actual = {Path(a) for a in sample.context}
        score = _score(predicted, actual)

        await mentat.shutdown()
        return score
    finally:
        os.chdir(starting_dir)


def main(user_samples: list[str], directory: str):
    # Load benchmarks
    dir_path = Path(directory).resolve()
    assert dir_path.exists(), f"Invalid directory: {directory}"
    print(f"Running benchmarks from {dir_path}")
    samples: list[Sample] = []
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            path = Path(root) / file
            if file.endswith(".json"):
                sample = Sample.load(path)
            else:
                continue
            if user_samples and not any(s in sample.title for s in user_samples):
                continue
            samples.append(sample)
    print("Found Samples:\n" + "\n".join(s.title for s in samples))
    print("*" * 80)

    config = Config(auto_context_tokens=8000)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_path = dir_path / f"context_benchmark_results_{timestamp}.jsonl"
    for sample in samples:
        print(f"Running benchmark for {sample.title}")
        accuracy = asyncio.run(run_auto_context_benchmark(sample, config, cwd=dir_path))
        print(f"Results: {accuracy}")
        print("*" * 80)
        with open(results_path, "a") as f:
            f.write(json.dumps({sample.id: accuracy}) + "\n")


if __name__ == "__main__":
    parser = common_benchmark_parser()
    args = parser.parse_args()
    if args.swe_bench:
        if args.swe_bench not in {"dev", "train", "test"}:
            print("Invalid SWE-Bench split.")
            exit(1)
        # Download and save SWE benchmarks as Samples
        samples = get_swe_samples(args.swe_bench, args.max_benchmarks)
        sample_titles = [sample.title for sample in samples]
        args.benchmarks = sample_titles
        args.directory = SWE_BENCH_SAMPLES_DIR / args.swe_bench
    main(
        args.benchmarks,
        args.directory,
    )
