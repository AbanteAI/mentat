import os
import shutil
import subprocess
from textwrap import dedent

import pytest

from mentat.session import Session

# These benchmarks use GPT and won't run automatically.
# Run them with python tests/record_benchmark.py True
# to record the results or use pytest --benchmark
# to not save the results.
pytestmark = pytest.mark.benchmark


async def edit_file_and_run(
    mock_collect_user_input, prompts, context_file_paths, main_file_path, argument_lists
):
    mock_collect_user_input.set_stream_messages(
        [prompt for pair in zip(prompts, ["y"] * len(prompts)) for prompt in pair]
        + ["q"]
    )

    session = await Session.create(context_file_paths)
    await session.start()
    await session.stream.stop()

    assert os.path.exists(main_file_path)

    results = []
    for arguments in argument_lists:
        result = subprocess.check_output(
            ["python", main_file_path, *arguments], text=True
        )
        results.append(result.strip())
    return results


@pytest.mark.asyncio
async def test_calculator_add_power(mock_collect_user_input):
    calculator_path = "scripts/calculator.py"
    results = await edit_file_and_run(
        mock_collect_user_input,
        prompts=[
            "Add power as a possible operation, raising the first arg to the power of"
            " the second"
        ],
        context_file_paths=[calculator_path],
        main_file_path=calculator_path,
        argument_lists=[["power", "15", "3"]],
    )
    assert float(results[0]) == 3375.0


@pytest.mark.asyncio
async def test_calculator_add_exp_then_log(mock_collect_user_input):
    calculator_path = "scripts/calculator.py"
    results = await edit_file_and_run(
        mock_collect_user_input,
        prompts=[
            "Add exponentation operation, called with 'exp'",
            "Add logarithm operation, called with 'log'",
        ],
        context_file_paths=[calculator_path],
        main_file_path=calculator_path,
        argument_lists=[["exp", "15", "3"], ["log", "10", "2"]],
    )
    assert float(results[0]) == 3375.0
    assert float(results[1]) == 3.3219280948873626


@pytest.mark.asyncio
async def test_calculator_continue_change(mock_collect_user_input):
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

    results = await edit_file_and_run(
        mock_collect_user_input,
        prompts=["complete the change I started"],
        context_file_paths=[calculator_path],
        main_file_path=calculator_path,
        argument_lists=[["exp", "15", "3"]],
    )
    assert float(results[0]) == 3375.0


@pytest.mark.asyncio
async def test_multifile_calculator(mock_collect_user_input):
    multifile_calculator_path = "multifile_calculator"
    calculator_path = os.path.join(multifile_calculator_path, "calculator.py")
    results = await edit_file_and_run(
        mock_collect_user_input,
        prompts=["add exp and log functions to take a^b and log a base b"],
        context_file_paths=[multifile_calculator_path],
        main_file_path=calculator_path,
        argument_lists=[["exp", "15", "3"], ["log", "10", "2"]],
    )

    assert float(results[0]) == 3375.0
    assert float(results[1]) == 3.3219280948873626


@pytest.mark.asyncio
async def test_start_project_from_scratch(mock_collect_user_input):
    # Clear the testbed so we can test that it works with empty directories
    for item in os.listdir("."):
        if os.path.isfile(item):
            os.remove(item)
        elif os.path.isdir(item):
            if item != ".git":
                shutil.rmtree(item)
    subprocess.run(["git", "rm", "-r", "--cached", "."])

    fizzbuzz_path = "fizzbuzz.py"
    results = await edit_file_and_run(
        mock_collect_user_input,
        prompts=["make a file that does fizzbuzz, named fizzbuzz.py, going up to 10"],
        context_file_paths=["."],
        main_file_path=fizzbuzz_path,
        argument_lists=[[]],
    )

    expected_output = "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz"
    assert results[0] == expected_output


@pytest.mark.asyncio
async def test_import_from_code_map(mock_collect_user_input):
    prompt = """
        make a file called encoded_echo.py that gets the base64 encoded value of
        `echo_hardcoded` and print the encoded value as a string
    """
    prompt = dedent(prompt).strip()
    encoded_echo_path = "encoded_echo.py"
    results = await edit_file_and_run(
        mock_collect_user_input,
        prompts=[prompt],
        context_file_paths=[],
        main_file_path=encoded_echo_path,
        argument_lists=[[]],
    )

    expected_output = "MDBtcDk0ITJQZ0slaTJoQG0mNVh6azRUJlZxQypOV1FebXA5NCEyUGdLJWkyaEBtJjVYems0VCZWcUMqTldRXg=="
    assert results[0] == expected_output
