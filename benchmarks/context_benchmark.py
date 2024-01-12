#!/usr/bin/env python
import asyncio
import json
import os
from collections import defaultdict
from itertools import islice
from pathlib import Path
from typing import Any

from git import Repo

from benchmarks.arg_parser import common_benchmark_parser
from mentat.code_context import CodeContext
from mentat.code_feature import CodeFeature
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config
from mentat.cost_tracker import CostTracker
from mentat.llm_api_handler import count_tokens, model_context_size
from mentat.sampler.utils import clone_repo
from mentat.session_context import SESSION_CONTEXT, SessionContext


class MockStream:
    def send(self, message, **kwargs):
        end = kwargs.get("end", "\n")
        print(message, end=end)


def _load_benchmarks() -> dict[str, dict[str, Any]]:
    """Load all benchmarks found in benchmark_repos"""
    benchmarks = {}
    benchmarks_dir = Path(__file__).parent / "../benchmark_repos"
    for repo_dir in benchmarks_dir.iterdir():
        benchmarks_path = repo_dir / "benchmarks.json"
        if benchmarks_path.exists():
            with open(benchmarks_path, "r") as f:
                benchmarks.update(json.load(f))
    return benchmarks


def _convert_features_to_line_sets(
    git_root: Path, features: list[CodeFeature]
) -> defaultdict[set]:
    """Convert a list of features to a dict of {path: set(lines)} for comparison"""
    lines = defaultdict(set)
    for feature in features:
        # Non-explicit features (e.g. CodeMaps) are considered false positives.
        # Using negative numbers here as that affect.

        path = feature.path.relative_to(git_root)
        interval = feature.interval
        lines[path].update(range(interval.start, interval.end + 1))
    return lines


def evaluate(
    git_root: Path,
    actual: list[CodeFeature],
    expected: list[CodeFeature],
) -> dict[str, float]:
    """Compare two lists of features and return precision, recall and f1 scores"""
    actual_lines = _convert_features_to_line_sets(git_root, actual)
    expected_lines = _convert_features_to_line_sets(git_root, expected)

    _TP, _FP, _FN = 0, 0, 0
    for file in actual_lines | expected_lines:
        actual_set = actual_lines[file]
        expected_set = expected_lines[file]
        _TP += len(actual_set & expected_set)
        _FP += len(actual_set - expected_set)
        _FN += len(expected_set - actual_set)

    precision, recall, f1 = None, None, None
    if (_TP + _FP) > 0:
        precision = _TP / (_TP + _FP)
    if (_TP + _FN) > 0:
        recall = _TP / (_TP + _FN)
    if precision and recall:
        f1 = 2 * precision * recall / (precision + recall)

    return {"precision": precision, "recall": recall, "f1": f1}


async def select_features_for_benchmark(
    session_context, benchmark, eval=True, use_expected=False, use_llm=True
):
    """Select features for benchmark using expected edits as a guide"""
    git_root = session_context.git_root
    config = session_context.config
    parser = config.parser
    code_context = session_context.code_context

    # The longest context that could have been included to generate expected_edits
    model = config.model
    mentat_prompt_tokens = count_tokens(parser.get_system_prompt(), model)
    expected_edits, expected_edits_tokens = None, 0
    if use_expected:
        expected_edits = benchmark["expected_edits"]
        expected_edits_tokens = count_tokens(expected_edits, model)
    max_context_tokens = (
        model_context_size(model) - mentat_prompt_tokens - expected_edits_tokens
    )
    # Fill-in available context
    config.auto_context_tokens = 8000
    code_context.use_llm = use_llm
    await code_context.get_code_message(
        benchmark["prompt"], max_context_tokens, expected_edits
    )
    git_root_length = len(str(git_root)) + 1
    selected_features = [f.ref()[git_root_length:] for f in code_context.features]

    selector_performance = {}
    if eval:
        edited_features = [
            CodeFeature(git_root / f) for f in benchmark["edited_features"]
        ]
        selector_performance = evaluate(
            git_root, code_context.features, edited_features
        )
    return {"features": selected_features, "score": selector_performance}


async def test_code_context_performance(benchmarks, max_benchmarks=10):
    """Run a set of benchmarks and evaluate performance

    Run standalone:
        `./benchmarks/context_benchmark.py`
    """
    # Load applicable benchmarks
    all_benchmarks = _load_benchmarks()
    if len(benchmarks) > 0:
        benchmarks_to_run = {k: v for k, v in all_benchmarks.items() if k in benchmarks}
    else:
        benchmarks_to_run = dict(islice(all_benchmarks.items(), max_benchmarks))

    # Run each one
    scores = {}
    for benchmark in benchmarks_to_run.values():
        print("\n" + benchmark["prompt"])

        # Setup the cwd the same way as in generate
        url = benchmark["codebase_url"]
        codebase = clone_repo(url=url, local_dir_name=url.split("/")[-1], refresh=False)
        os.chdir(codebase)
        repo = Repo(".")
        repo.git.checkout(benchmark["commit"])

        # Initialize a full SESSION_CONTEXT
        stream = MockStream()
        config = Config()
        code_context = CodeContext(stream, os.getcwd())
        session_context = SessionContext(
            stream,
            CostTracker(),
            Path.cwd(),
            config,
            code_context,
            CodeFileManager(),
            None,
        )
        SESSION_CONTEXT.set(session_context)

        # Run the benchmark and print results
        scores = []
        for use_llm in [False, True]:
            for use_expected in [False, True]:
                try:
                    if not use_llm and use_expected:
                        continue  # Not relevant
                    results = await select_features_for_benchmark(
                        session_context,
                        benchmark,
                        eval=True,
                        use_expected=use_expected,
                        use_llm=use_llm,
                    )
                    score = {
                        **results["score"],
                        "selected_features": results["features"],
                        "edited_features": benchmark["edited_features"],
                        "use_llm": use_llm,
                        "use_expected": use_expected,
                    }
                    scores.append(score)
                    print(
                        f"  UseExpected={use_expected}\t"
                        f"| LLM={use_llm}\t"
                        f"| Recall={(score['recall'] or 0.):.3f}\t"
                        f"| Precision={(score['precision'] or 0.):.3f}"
                    )
                except Exception as e:
                    print(f"Error: '{e}'; skipping")

    return scores


if __name__ == "__main__":
    parser = common_benchmark_parser()
    args = parser.parse_args()
    asyncio.run(
        test_code_context_performance(
            args.benchmarks,
            args.max_benchmarks,
        )
    )
