import json
import os
from textwrap import dedent
from unittest.mock import patch

import pytest

from benchmarks.exercism_practice import run_exercism_benchmark


@pytest.fixture
def mock_webbrowser():
    with patch("webbrowser.open") as mock:
        yield mock


class MockPool:
    def __init__(self, processes):
        self.processes = processes

    def imap(self, func, iterable):
        return map(func, iterable)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_pool():
    with patch("multiprocessing.Pool", new=MockPool) as mock:
        yield mock


def test_run_exercism_benchmark(mock_pool, mock_webbrowser, mock_call_llm_api):
    os.chdir("exercism-python")
    cwd = os.getcwd()
    mock_call_llm_api.set_return_values(
        [
            dedent(
                """\
            test

            @@start
            {
                "file": "exercises/practice/accumulate/accumulate.py",
                "action": "replace",
                "start-line": 1,
                "end-line": 2
            }
            @@code
            def accumulate(collection, operation):
                result = []
                for item in collection:
                    result.append(operation(item))
                return result
            @@end"""
            ),
            dedent(
                """\
            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 5,
                "end-line": 6
            }
            @@code
                def personal_best(self):
                    return max(self.scores)
            @@end"""
            ),
            dedent(
                """\
            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 8,
                "end-line": 9
            }
            @@code
                def latest(self):
                    return self.scores[-1]
            @@end

            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 11,
                "end-line": 12
            }
            @@code
                def personal_top_three(self):
                    return sorted(self.scores, reverse=True)[:3]
            @@end"""
            ),
            dedent(
                """\
            grading example
            reason: logic"""
            ),
        ]
    )
    run_exercism_benchmark(
        ["accumulate", "high-scores"],
        2,
        2,
        1,
        "python",
    )
    assert os.getcwd() == cwd
    with open("results.json") as f:
        results = json.load(f)
    assert len(results["results"]) == 2
    with open("summary/results.json") as f:
        summary = json.load(f)
    summary = summary["summary"]
    assert summary["passed"] == [50.0, 2]
