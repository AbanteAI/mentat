from .abstract_exercise_runner import AbstractExerciseRunner


class PythonExerciseRunner(AbstractExerciseRunner):
    def __init__(self, exercise):
        super().__init__(exercise, "py")
        self.exercise_file = self.exercise_file.replace("-", "_")
        self.exercise_full_path = f"{self.exercise_dir}/{self.exercise_file}"

    def run_test(self):
        self._run_test_command(["pytest", self.exercise_dir])

    def exercise_passed(self):
        try:
            with open(self.test_output_file, "r") as f:
                lines = f.readlines()
                return "failed" not in lines[-1] and "passed" in lines[-1]
        except FileNotFoundError:
            return False
