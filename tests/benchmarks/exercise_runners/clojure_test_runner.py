from pathlib import Path

from tests.benchmarks.exercise_runners.abstract_exercise_runner import (
    AbstractExerciseRunner,
)


class ClojureTestRunner(AbstractExerciseRunner):
    def __init__(self, exercise):
        super().__init__(exercise, "clj")
        self.test_file = self.dir / Path(f"{exercise}_test.clj")

    def run_test(self):
        self._run_test_command(["lein", "test"], cwd=self.dir)

    def passed(self):
        try:
            with open(self.test_output_file, "r") as f:
                lines = f.readlines()
                return (
                    "Ran all tests." in lines[-1]
                    and "0 failures, 0 errors." in lines[-1]
                )
        except FileNotFoundError:
            return False
