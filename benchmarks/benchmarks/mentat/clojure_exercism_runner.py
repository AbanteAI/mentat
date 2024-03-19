from mentat.config import Config

title = "Clojure Exercism Runner"

description = """
This benchmark tests the ability to write an exercism test runner for the clojure language.
"""

prompts = [
    "Write a test runner for the clojure language.",
]


repo = "https://github.com/AbanteAI/mentat"
commit = "d611e2ff742856c7328d54f6e71c2418f9c5508b"
minimum_context = ["tests/benchmarks/exercise_runners"]
paths = []

config = Config(
    auto_context_tokens=8000,
    maximum_context=8000,
)


def verify():
    try:
        from benchmark_repos.mentat.tests.benchmarks.exercise_runners.clojure_exercise_runner import (
            ClojureExerciseRunner,
        )
        from benchmark_repos.mentat.tests.benchmarks.exercise_runners.exercise_runner_factory import (
            ExerciseRunnerFactory,
        )

        added_to_factory = ExerciseRunnerFactory.RUNNERS["clojure"] == ClojureExerciseRunner

        made_runner = hasattr(ClojureExerciseRunner, "run_test")
        made_runner = made_runner and hasattr(ClojureExerciseRunner, "passed")

        return added_to_factory and made_runner
    except Exception:
        return False
