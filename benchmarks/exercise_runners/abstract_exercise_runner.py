import os
import subprocess
from pathlib import Path

from benchmarks.benchmark_result import BenchmarkResult


class AbstractExerciseRunner:
    def __init__(self, exercise, extension):
        self.name = exercise
        self.dir = Path(f"exercises/practice/{exercise}").absolute()
        self.file = Path(f"{exercise}.{extension}")
        self.full_path = self.dir / self.file
        self.test_output_file = self.dir / "test_output.txt"

    def _run_test_command(self, command, cwd="."):
        try:
            proc = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=5,
                cwd=cwd,
            )
            results = proc.stdout.decode("utf-8")
        except subprocess.TimeoutExpired:
            results = "Test timed out"
        with open(self.test_output_file, "w") as f:
            f.write(results.strip())

    def include_files(self):
        return [self.full_path, self.docs()]

    def exclude_files(self):
        return [self.docs() / "hints.md"]

    def docs(self):
        return self.dir / ".docs"

    def get_result_from_txt(self):
        if not Path("results.txt").exists():
            return None
        with open("results.txt", "r") as f:
            for line in f.readlines():
                if f'"{self.name}"' in line:
                    return BenchmarkResult.from_json(line)

    def get_error_message(self):
        with open(self.test_output_file, "r") as f:
            lines = f.readlines()
            lines = lines[:50]
            return "\n".join(lines)

    # This will include hint.md
    def read_instructions(self):
        instructions = ""
        for file_name in os.listdir(self.docs()):
            with open(self.docs() / file_name) as f:
                contents = f.read()
                instructions += f"{file_name}\n{contents}\n"
        return instructions

    def read_code(self, language):
        code = ""
        with open(self.full_path) as f:
            contents = f.read()
            code += f"{self.file}\n{contents}"
        return code

    def read_test_results(self):
        if not self.test_output_file.exists():
            return ""
        with open(self.test_output_file) as f:
            contents = f.read()
            test_results = f"test_output.txt\n{contents}"
        return test_results
