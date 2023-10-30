"""
Given a codebase, a prompt and a token limit, code_context will auto-select
features to include in the code_message. This script evaluates the 
performance of that selection algorithm.

Test Guidelines:
- Codebase should be larger than the token limit
- Prompts should be thorough and specific - give it the best chance to succeed
- Tasks should draw on multiple files/features.

Scoring:
- Score based on the features (path, level, diff) auto-selected
- Use traditional precision, recall and f1 scores:
    - y_pred = [(f in code_context.features) for f in all_features]
    - y_true = [(f in test.expected) for f in all_features]

Fine-tuning:
An auto-context process might look like this:
1. Use local methods (embeddings) to select a full-context worth
    of features
2. Send the code_message of those features to gpt-3, and have it 
    return a modified features spec [(path, level, diff)] based on what's
    relevant and not. (Bonus: let gpt-3 ask for more info if it needs it)
3. Use the modified features to get_code_message for gpt-4

These tests can be used to train/score #1 or #2, but we'd expect #2 to score 
a lot higher.
"""

import json
import os
from collections import defaultdict
from itertools import islice
from pathlib import Path
from typing import Any

import pytest
from git import Repo

from mentat.code_context import CodeContext
from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.code_file_manager import CodeFileManager
from mentat.config import Config
from mentat.llm_api import CostTracker, setup_api_key
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session_context import SESSION_CONTEXT, SessionContext
from scripts.git_log_to_transcripts import MockStream
from tests.benchmarks.utils import clone_repo

pytestmark = pytest.mark.benchmark

benchmarks_dir = Path(__file__).parent / "repos/for_transcripts"


def load_tests() -> dict[str, dict[str, Any]]:
    tests = {}
    benchmarks_path = benchmarks_dir / "benchmarks.json"
    if benchmarks_path.exists():
        with open(benchmarks_path, "r") as f:
            tests = json.load(f)
    return tests


def features_to_line_sets(
    git_root: Path, features: list[CodeFeature]
) -> defaultdict[set]:
    lines = defaultdict(set)
    for feature in features:
        # Non-explicit features (e.g. CodeMaps) are considered false positives.
        # Using negative numbers here as that affect.
        if feature.level not in (CodeMessageLevel.CODE, CodeMessageLevel.INTERVAL):
            n_lines = len(feature.get_code_message())
            lines[feature.path].update(range(-1, -n_lines - 1, -1))
            continue

        # Otherwise match specific lines
        path = feature.path.relative_to(git_root)
        if feature.level == CodeMessageLevel.INTERVAL:
            intervals = [(f.start, f.end) for f in feature.intervals]
        else:
            n_lines = len(feature.get_code_message())
            intervals = [(1, n_lines + 1)]
        for start, end in intervals:
            lines[path].update(range(start, end + 1))
    return lines


def evaluate(
    git_root: Path, actual: list[CodeFeature], expected: list[CodeFeature]
) -> dict[str, float]:
    actual_lines = features_to_line_sets(git_root, actual)
    expected_lines = features_to_line_sets(git_root, expected)

    _TP, _FP, _FN = 0, 0, 0
    for file in actual_lines | expected_lines:
        actual_set = actual_lines[file]
        expected_set = expected_lines[file]
        _TP += len(actual_set & expected_set)
        _FP += len(actual_set - expected_set)
        _FN += len(expected_set - actual_set)

    print(f"True Positive:\t{_TP:.3f}")
    print(f"False Positive:\t{_FP:.3f}")
    print(f"False Negative:\t{_FN:.3f}")

    precision, recall = None, None
    if (_TP + _FP) > 0:
        precision = _TP / (_TP + _FP)
        print(
            f"Precision:\t{precision:.3f}\t| How many selected features are relevant?"
        )
    if (_TP + _FN) > 0:
        recall = _TP / (_TP + _FN)
        print(f"Recall:\t\t{recall:.3f}\t| How many relevant features are selected?")
    if precision and recall:
        f1 = 2 * precision * recall / (precision + recall)
        print(f"F1:\t\t{f1:.3f}\t| Weighted average of precision and recall")


@pytest.mark.asyncio
async def test_code_context_performance(
    mock_session_context, benchmarks, max_benchmarks
):
    setup_api_key()
    tests = load_tests()

    if len(benchmarks) > 0:
        tests_to_run = {k: v for k, v in tests.items() if k in benchmarks}
    else:
        tests_to_run = dict(islice(tests.items(), max_benchmarks))

    for test in tests_to_run.values():
        print(f"\n\n{test['name']}\n{test['prompt']}")

        # Setup the cwd the same way as in generate
        codebase = clone_repo(test["codebase_url"], "for_transcripts")
        os.chdir(codebase)

        # Initialize a full SESSION_CONTEXT
        stream = MockStream()
        git_root = Path.cwd()
        config = Config(use_embeddings=True, auto_tokens=7000)
        code_context = CodeContext(stream, os.getcwd())
        paths = test["args"].get("paths", [])
        exclude_paths = test["args"].get("exclude_paths", [])
        ignore_paths = test["args"].get("ignore_paths", [])
        code_context.set_paths(paths, exclude_paths, ignore_paths)
        session_context = SessionContext(
            stream,
            CostTracker(),
            git_root,
            config,
            ReplacementParser(),
            code_context,
            CodeFileManager(),
            None,
        )
        SESSION_CONTEXT.set(session_context)
        repo = Repo(".")
        repo.git.checkout(test["commit"])

        # Get results with and without llm
        expected_features = [
            CodeFeature(git_root / f) for f in test["expected_features"]
        ]

        _ = await code_context.get_code_message(test["prompt"], "gpt-4", 7000)
        evaluate(git_root, code_context.features, expected_features)

        code_context.use_llm = True
        _ = await code_context.get_code_message(test["prompt"], "gpt-4", 7000)
        evaluate(git_root, code_context.features, expected_features)
