from benchmarks.exercise_runners.clojure_exercise_runner import ClojureExerciseRunner
from benchmarks.exercise_runners.javascript_exercise_runner import (
    JavascriptExerciseRunner,
)
from benchmarks.exercise_runners.python_exercise_runner import PythonExerciseRunner


class ExerciseRunnerFactory:
    RUNNERS = {
        "clojure": ClojureExerciseRunner,
        "javascript": JavascriptExerciseRunner,
        "python": PythonExerciseRunner,
    }

    @classmethod
    def create(cls, language, exercise):
        return cls.RUNNERS[language](exercise)
