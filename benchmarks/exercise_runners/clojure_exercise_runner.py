from pathlib import Path

from benchmarks.exercise_runners.abstract_exercise_runner import AbstractExerciseRunner


class ClojureExerciseRunner(AbstractExerciseRunner):
    def __init__(self, exercise):
        super().__init__(exercise, "clj")
        self.file = Path(exercise.replace("-", "_") + ".clj")
        self.full_path = self.dir / "src" / self.file

    def run_test(self):
        self._run_test_command(
            ["lein", "test", ":only", self.name + "-test"], cwd=self.dir
        )

    def passed(self):
        try:
            with open(self.test_output_file, "r") as f:
                lines = f.readlines()
                return "0 failures, 0 errors." in lines[-1]
        except FileNotFoundError:
            return False
