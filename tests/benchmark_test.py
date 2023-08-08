import importlib
import os
import shutil
import subprocess
import sys

import pytest

from mentat.app import run

# These benchmarks use GPT and won't run automatically.
# Run them with python tests/record_benchmark.py True
# to record the results or use pytest --benchmark
# to not save the results.
pytestmark = pytest.mark.benchmark


def test_calculator_add_power(mock_collect_user_input):
    mock_collect_user_input.side_effect = [
        (
            "Add power as a possible operation, raising the first arg to the power of"
            " the second"
        ),
        "y",
        KeyboardInterrupt,
    ]

    calculator_path = os.path.join("scripts/calculator.py")
    run([calculator_path])

    result = subprocess.run(
        ["python", calculator_path, "power", "15", "3"], capture_output=True, text=True
    )
    assert float(result.stdout.strip()) == 3375.0


def test_calculator_add_exp_then_log(mock_collect_user_input):
    mock_collect_user_input.side_effect = [
        "Add exponentation operation, called with 'exp'",
        "y",
        "Add logarithm operation, called with 'log'",
        "y",
        KeyboardInterrupt,
    ]

    calculator_path = "scripts/calculator.py"
    run([calculator_path])

    result = subprocess.run(
        ["python", calculator_path, "exp", "15", "3"], capture_output=True, text=True
    )
    assert float(result.stdout.strip()) == 3375.0

    result = subprocess.run(
        ["python", calculator_path, "log", "10", "2"], capture_output=True, text=True
    )
    assert float(result.stdout.strip()) == 3.3219280948873626


def test_calculator_continue_change(mock_collect_user_input):
    mock_collect_user_input.side_effect = [
        "complete the change I started",
        "y",
        KeyboardInterrupt,
    ]

    calculator_path = "scripts/calculator.py"

    with open(calculator_path, "r") as f:
        calculator_lines = f.readlines()
    index = calculator_lines.index("    return a / b\n")
    new_lines = [
        "\n",
        "\n",
        "def exp_numbers(a, b):\n",
        "    return a**b\n",
    ]
    calculator_lines = (
        calculator_lines[: index + 1] + new_lines + calculator_lines[index + 1 :]
    )
    with open(calculator_path, "w") as f:
        f.writelines(calculator_lines)

    run([calculator_path])

    result = subprocess.run(
        ["python", calculator_path, "exp", "15", "3"], capture_output=True, text=True
    )
    assert float(result.stdout.strip()) == 3375.0


def test_multifile_calculator(mock_collect_user_input):
    mock_collect_user_input.side_effect = [
        "add exp and log functions to take a^b and log a base b",
        "y",
        KeyboardInterrupt,
    ]

    multifile_calculator_path = "multifile_calculator"
    calculator_path = os.path.join(multifile_calculator_path, "calculator.py")

    run([multifile_calculator_path])
    result = subprocess.run(
        ["python", calculator_path, "exp", "15", "3"], capture_output=True, text=True
    )
    assert float(result.stdout.strip()) == 3375.0

    result = subprocess.run(
        ["python", calculator_path, "log", "10", "2"], capture_output=True, text=True
    )
    assert float(result.stdout.strip()) == 3.3219280948873626


def test_start_project_from_scratch(mock_collect_user_input):
    # Clear the testbed so we can test that it works with empty directories
    for item in os.listdir("."):
        if os.path.isfile(item):
            os.remove(item)
        elif os.path.isdir(item):
            if item != ".git":
                shutil.rmtree(item)

    mock_collect_user_input.side_effect = [
        "make a file that does fizzbuzz, named fizzbuzz.py, going up to 10",
        "y",
        KeyboardInterrupt,
    ]
    run(["."])

    fizzbuzz_path = "fizzbuzz.py"
    assert os.path.exists(fizzbuzz_path)

    result = subprocess.run(["python", fizzbuzz_path], capture_output=True, text=True)
    expected_output = "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n"
    assert result.stdout.strip() == expected_output.strip()


def import_module_from_path(module_name, relative_file_path):
    """
    Imports a from the file Mentat just edited.
    import in Python is always relative to the file's original path so
    even though we change the cwd, we can't use relative imports to import from the tmp dir.

    I don't really know what module_name is for since it even works as the empty string.
    Docs: https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly

    @param module_name: "." separated path from and including testbed
    @param relative_file_path: The path to the file to import from relative to and excluding testbed
    """
    file_path = os.path.join(os.getcwd(), relative_file_path)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_create_person_class_from_data(mock_collect_user_input, temp_testbed):
    # I had to add details/ hints to prompt engineer this until the model began passing the test
    # If we want to make the test more challenging, the parts we can remove are:
    """
    Make sure to pay special attention to the nuances of loading the data.
    In this data file people are stored either as parents, children, or standalone.
    Each one needs to be included.
    """
    # Those three lines are things users shouldn't have to specify - since mentat can read the data.json file
    # But mentat can't consistently pass without them

    # these tests were run on commit c91548c
    # 20 runs each probably isn't enough to be confident in the pass rate

    # 19 passed, 1 failed - 95% pass rate
    easy_prompt = (  # noqa F841
        "Fill out the Person class for this data. It needs load_data and __eq__"
        " functions. The equality functions should compare all attributes and"
        " recursively compare the parents. A Person should have individual mother"
        " and father attributes. The load_data function should be a class method of"
        " Person. The load function will take the data file's path as an argument."
        " Make sure to pay special attention to the nuances of loading the data. In"
        " this data file people are stored either as parents, children, or"
        " standalone. Each one needs to be included. Note that the father is listed"
        " first in a parents list."
    )
    # Removes the line: "Make sure to pay special attention to the nuances of loading the data."
    # 15 passed, 5 failed - 75% pass rate
    easy_medium_prompt = (
        "Fill out the Person class for this data. It needs load_data and __eq__"
        " functions. The equality functions should compare all attributes and"
        " recursively compare the parents. A Person should have individual mother"
        " and father attributes. The load_data function should be a class method of"
        " Person. The load function will take the data file's path as an argument."
        " In this data file people are stored either as parents, children, or"
        " standalone. Each one needs to be included. Note that the father is listed"
        " first in a parents list."
    )
    # Removes the line: "Each one needs to be included."
    # 8 passed, 12 failed - 40% pass rate
    medium_prompt = (  # noqa F841
        "Fill out the Person class for this data. It needs load_data and __eq__"
        " functions. The equality functions should compare all attributes and"
        " recursively compare the parents. A Person should have individual mother"
        " and father attributes. The load_data function should be a class method of"
        " Person. The load function will take the data file's path as an argument."
        " In this data file people are stored either as parents, children, or"
        " standalone. Note that the father is listed first in a parents list."
    )
    # Removes the Line: "In this data file people are stored either as parents, children, or standalone."
    # Probably 0% pass rate (I ran it a number of times)
    hard_prompt = (  # noqa F841
        "Fill out the Person class for this data. It needs load_data and __eq__"
        " functions. The equality functions should compare all attributes and"
        " recursively compare the parents. A Person should have individual mother"
        " and father attributes. The load_data function should be a class method of"
        " Person. The load function will take the data file's path as an argument."
        " Note that the father is listed"
        " first in a parents list."
    )
    mock_collect_user_input.side_effect = [
        easy_medium_prompt,
        "y",
        KeyboardInterrupt,
    ]
    run(["person_data/data.json", "person_data/person.py"])

    relative_file_path = "person_data/person.py"
    Person = import_module_from_path("", relative_file_path).Person
    # from testbed.person_data.solution_person import Person

    people = Person.load_data("../testbed/person_data/data.json")

    # One of the most common mistakes Mentat makes:
    assert (
        len(people) != 14
    ), "Mentat likely duplicated the parents (counted them for each child)"
    assert len(people) != 8, "Mentat likely didn't include the parents"
    assert len(people) == 10, f"Mentat gave the wrong number of people ({len(people)})"

    assert sorted(list(vars(people[0]).keys())) == [
        "age",
        "father",
        "married",
        "mother",
        "name",
        "weight",
    ]

    def sortkey(x):
        return (x.name, x.age, x.weight, x.married, x.father, x.mother)

    people = sorted(people, key=sortkey)
    people2 = sorted(Person.load_data("../testbed/person_data/data.json"), key=sortkey)
    for p1, p2 in zip(people, people2):
        assert p1 == p2

    # this tests that the __eq__ function compares all attributes
    # the 5 "janes" (one named fridge), when compared pairwise, each differ by only one attribute
    for p1, p2 in zip(people[:-1], people2[1:]):
        assert p1 != p2

    people3 = sorted(
        Person.load_data("../testbed/person_data/test_data.json"), key=sortkey
    )
    # This tests that the equality function is recursive - because the Alexs' moms' ages are different
    assert people[0].name == people3[0].name == "Alex"
    assert people[0] != people3[0]
