import os
import shutil
import subprocess

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
