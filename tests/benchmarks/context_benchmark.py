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
import os
import subprocess

import pytest

from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.git_handler import get_non_gitignored_files
from mentat.llm_api import setup_api_key
from tests.benchmarks.utils import clone_repo

pytestmark = pytest.mark.benchmark

tests = [
    {
        "name": "Mentat: replace subprocess/git with GitPython",
        "codebase_url": "http://github.com/AbanteAI/mentat",
        "codebase_name": "mentat",
        "commit": "a9f055e",
        "prompt": (
            "I want to update all the files in git_handler to use the 'Repo' class from"
            " GitPython instead of calling subprocess. Update each function in"
            " mentat/git_handler.py that calls subprocess to use Repo instead. If git"
            " is run with subprocess anywhere in the code, update those as well."
        ),
        "expected_features": [
            "mentat/git_handler.py",
            "mentat/diff_context.py:173-179",
            "tests/benchmark_test.py:118-139",
            "tests/commands_test.py:26-34",
            "tests/conftest.py:259-266",
            "tests/diff_context_test.py",
            "tests/git_handler_test.py:23-30",
            "tests/clients/terminal_client_test.py:62-93",
        ],
        "expected_edits": [
            # for other benchmarks
        ],
    },
]


@pytest.mark.asyncio
async def test_code_context_performance(mock_session_context):
    setup_api_key()

    for test in tests:
        print(f"\n\n{test['codebase_name']}/ \t '{test['prompt'][:50]}...'")

        code_dir = clone_repo(test["codebase_url"], test["codebase_name"])
        os.chdir(code_dir)
        if test["commit"]:
            subprocess.run(["git", "checkout", test["commit"]])

        mock_session_context.git_root = code_dir
        code_context = mock_session_context.code_context

        # Create a context and run get_code_message to set the features
        code_context.include_file("mentat/__init__.py")
        code_context.settings.use_embeddings = True
        code_context.settings.auto_tokens = 7000
        _ = await code_context.get_code_message(test["prompt"], "gpt-4", 7000)

        # Calculate y_pred and y_true
        actual = {
            f.path for f in code_context.features if f.level == CodeMessageLevel.CODE
        }
        expected_features = {
            CodeFeature(f).path for f in test["expected_features"]
        }  # Ignore line numbers for now
        y_pred = [f in actual for f in get_non_gitignored_files(code_dir)]
        y_true = [f in expected_features for f in get_non_gitignored_files(code_dir)]

        _TP = sum([1 for p, t in zip(y_pred, y_true) if p and t])
        _TN = sum([1 for p, t in zip(y_pred, y_true) if not p and not t])
        _FP = sum([1 for p, t in zip(y_pred, y_true) if p and not t])
        _FN = sum([1 for p, t in zip(y_pred, y_true) if not p and t])
        print(f"True Positive:\t{_TP:.3f}")
        print(f"True Negative:\t{_TN:.3f}")
        print(f"False Positive:\t{_FP:.3f}")
        print(f"False Negative:\t{_FN:.3f}")

        precision, recall = None, None
        if (_TP + _FP) > 0:
            precision = _TP / (_TP + _FP)
            print(
                f"Precision:\t{precision:.3f}\t| How many selected features are"
                " relevant?"
            )
        if (_TP + _FN) > 0:
            recall = _TP / (_TP + _FN)
            print(
                f"Recall:\t\t{recall:.3f}\t| How many relevant features are selected?"
            )
        if precision and recall:
            f1 = 2 * precision * recall / (precision + recall)
            print(f"F1:\t\t{f1:.3f}\t| Weighted average of precision and recall")
