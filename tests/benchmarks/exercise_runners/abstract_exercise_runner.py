import os
import subprocess


class AbstractExerciseRunner:
    def __init__(self, exercise):
        self.exercise = exercise
        self.exercise_dir = f"exercises/practice/{exercise}"
        self.exercise_file = f"{self.exercise_dir}/{exercise}.js"
        self.test_output_file = f"{self.exercise_dir}/test_output.txt"

    def _run_test_command(self, command):
        try:
            proc = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5
            )
            results = proc.stdout.decode("utf-8")
        except subprocess.TimeoutExpired:
            results = "Test timed out"
        with open(self.test_output_file, "w") as f:
            f.write(results)

    def already_ran(self):
        return os.path.exists(self.test_output_file)

    def get_error_message(self):
        with open(self.test_output_file, "r") as f:
            lines = f.readlines()
            lines = lines[:50]
            return "\n".join(lines)
