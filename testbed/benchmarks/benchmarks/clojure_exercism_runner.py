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
paths = ["tests/benchmarks/exercise_runners"]

config = Config()
