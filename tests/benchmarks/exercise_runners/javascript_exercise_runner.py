import os
import subprocess

from .abstract_exercise_runner import AbstractExerciseRunner


class JavascriptExerciseRunner(AbstractExerciseRunner):
    def __init__(self, exercise):
        super().__init__(exercise, "js")
        if not os.path.exists("node_modules"):
            subprocess.run(["npm", "install"], stdout=subprocess.PIPE)

    def run_test(self):
        self._run_test_command(["./node_modules/jest/bin/jest.js", self.dir])

    def passed(self):
        try:
            with open(self.test_output_file, "r") as f:
                lines = f.readlines()
                return "FAIL" not in lines[0] and "PASS" in lines[0]
        except FileNotFoundError:
            return False
