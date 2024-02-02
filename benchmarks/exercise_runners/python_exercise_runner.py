from pathlib import Path

from benchmarks.exercise_runners.abstract_exercise_runner import AbstractExerciseRunner


class PythonExerciseRunner(AbstractExerciseRunner):
    def __init__(self, exercise):
        super().__init__(exercise, "py")
        self.file = Path(str(self.file).replace("-", "_"))
        self.full_path = self.dir / self.file

    def run_test(self):
        self._run_test_command(["pytest", self.dir])

    def passed(self):
        try:
            with open(self.test_output_file, "r") as f:
                lines = f.readlines()
                return "failed" not in lines[-1] and "passed" in lines[-1]
        except FileNotFoundError:
            return False
