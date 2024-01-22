import asyncio
import json
import os
from pathlib import Path
from typing import Any

from benchmarks.arg_parser import common_benchmark_parser
from benchmarks.run_sample import setup_python_client
from mentat.sampler.sample import Sample
from mentat.session_context import SESSION_CONTEXT


async def run_auto_context_benchmark(
    sample: Sample, cwd: Path | str | None = None
) -> dict[str, Any]:
    """Run a sample using Mentat and return the resulting diff"""
    python_client = await setup_python_client(sample, cwd)

    session_context = SESSION_CONTEXT.get()
    code_context = session_context.code_context
    config = session_context.config
    cwd = session_context.cwd

    expected_files = {c for c in sample.context}

    async def score():
        _ = await code_context.get_code_message(0, sample.message_prompt)
        features = {feature.rel_path(cwd) for feature in code_context.auto_features}
        true_positives = features.intersection(expected_files)
        false_positives = features.difference(expected_files)
        false_negatives = expected_files.difference(features)
        precision = len(true_positives) / (len(true_positives) + len(false_positives))
        recall = len(true_positives) / (len(true_positives) + len(false_negatives))
        return {"precision": precision, "recall": recall}

    config.auto_context_tokens = 8000
    embedding_only_score = await score()

    config.llm_feature_filter = 8000
    feature_filter_score = await score()

    await python_client.shutdown()

    return {
        "id": sample.id,
        "title": sample.title,
        "embedding_only_score": embedding_only_score,
        "feature_filter_score": feature_filter_score,
    }


def main(directory: str):
    # Load benchmarks
    dir_path = Path(directory).resolve()
    assert dir_path.exists(), f"Invalid directory: {directory}"

    results: list[dict[str, Any]] = []
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            path = Path(root) / file
            if file.endswith(".json"):
                sample = Sample.load(path)

                # TODO Skip results with context added or removed
                # TODO Generate a summary
                # TODO Add to benchmark/summary results
                # TODO Add auto-context precision/recall to BenchmarkResultSummary
                result = asyncio.run(run_auto_context_benchmark(sample))
                print(result)
                results.append(result)

    # Save results
    results_path = dir_path / "context_benchmark_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    parser = common_benchmark_parser()
    args = parser.parse_args()
    main(
        args.directory,
    )
