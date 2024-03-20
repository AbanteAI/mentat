import json
import os
from textwrap import dedent
from unittest.mock import patch

import pytest

from benchmarks.benchmark_runner import run_benchmarks


@pytest.fixture
def mock_webbrowser():
    with patch("webbrowser.open") as mock:
        yield mock


def test_run_real_world_benchmark(mock_webbrowser, mock_call_llm_api):
    cwd = os.getcwd()
    mock_call_llm_api.set_return_values(
        [
            dedent(
                """\
                Here are the code changes:

                @@start
                {
                    "file": "tests/benchmarks/exercise_runners/clojure_exercise_runner.py",
                    "action": "create-file"
                }
                @@code
                from .abstract_exercise_runner import AbstractExerciseRunner
                import subprocess
                import os


                class ClojureExerciseRunner(AbstractExerciseRunner):
                    def __init__(self, exercise):
                        super().__init__(exercise, "clj")
                        self.file = self.file.with_suffix(".clj")
                        self.full_path = self.dir / self.file

                    def run_test(self):
                        self._run_test_command(["lein", "test"], cwd=str(self.dir))

                    def passed(self):
                        try:
                            with open(self.test_output_file, "r") as f:
                                lines = f.readlines()
                                return "FAIL" not in lines[0] and "PASS" in lines[0]
                        except FileNotFoundError:
                            return False
                @@end

                @@start
                {
                    "file": "tests/benchmarks/exercise_runners/exercise_runner_factory.py",
                    "action": "insert",
                    "insert-after-line": 2,
                    "insert-before-line": 3
                }
                @@code
                from .clojure_exercise_runner import ClojureExerciseRunner
                @@end

                @@start
                {
                    "file": "tests/benchmarks/exercise_runners/exercise_runner_factory.py",
                    "action": "insert",
                    "insert-after-line": 7,
                    "insert-before-line": 8
                }
                @@code
                        "clojure": ClojureExerciseRunner,
                @@end"""
            ),
            dedent(
                """\
            {
                "indentation": false,
                "off_by_one": false,
                "syntax": false
            }"""
            ),
            dedent(
                """\
            {
                "referenced_format": true,
                "trailing_waffling": false
            }"""
            ),
        ]
    )
    run_benchmarks(["Clojure Exercism Runner"], "benchmarks/benchmarks")
    assert os.getcwd() == cwd
    with open("results.json") as f:
        results = json.load(f)
    assert results["results"][0]["response_grade"]["referenced_format"]
    with open("summary/results.json") as f:
        summary = json.load(f)
    summary = summary["summary"]
    assert summary["cost"] == [0, 1]
