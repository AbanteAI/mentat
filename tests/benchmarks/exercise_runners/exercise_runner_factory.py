from .clojure_exercise_runner import ClojureExerciseRunner
from .javascript_exercise_runner import JavascriptExerciseRunner
from .python_exercise_runner import PythonExerciseRunner


class ExerciseRunnerFactory:
    RUNNERS = {
        "clojure": ClojureExerciseRunner,
        "javascript": JavascriptExerciseRunner,
        "python": PythonExerciseRunner,
    }

    @classmethod
    def create(cls, language, exercise):
        return cls.RUNNERS[language](exercise)
