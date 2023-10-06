import os
from pathlib import Path
from textwrap import dedent

import pytest

from mentat.session import Session


# Make sure we always give posix paths to GPT
@pytest.mark.asyncio
async def test_posix_paths(
    mock_stream, mock_config, mock_code_file_manager, mock_code_context
):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = Path(os.path.join(dir_name, file_name))
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")

    mock_code_context.settings.paths = [file_path]
    await mock_code_context.refresh(True)

    mock_code_file_manager.read_all_file_lines()
    code_message = await mock_code_context.get_code_message(
        mock_code_file_manager.file_lines, mock_config.model(), True
    )
    assert dir_name + "/" + file_name in code_message.split("\n")


@pytest.mark.asyncio
async def test_partial_files(
    mock_stream, mock_config, mock_code_file_manager, mock_code_context
):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = os.path.join(dir_name, file_name)
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write(dedent("""\
             I am a file
             with 5 lines
             third
             fourth
             fifth"""))

    file_path_partial = file_path + ":1,3-5"
    mock_code_context.settings.paths = [Path(file_path_partial)]
    await mock_code_context.refresh(True)
    mock_code_context.code_map = None

    mock_code_file_manager.read_all_file_lines()
    code_message = await mock_code_context.get_code_message(
        mock_code_file_manager.file_lines, mock_config.model(), True
    )
    assert code_message == dedent("""\
            Code Files:

            dir/file.txt
            1:I am a file
            3:third
            4:fourth
            5:fifth
              """)


@pytest.mark.asyncio
async def test_run_from_subdirectory(
    mock_collect_user_input, mock_call_llm_api, mock_setup_api_key
):
    """Run mentat from a subdirectory of the git root"""
    # Change to the subdirectory
    os.chdir("multifile_calculator")
    mock_collect_user_input.set_stream_messages(
        [
            (
                "Insert the comment # Hello on the first line of"
                " multifile_calculator/calculator.py and scripts/echo.py"
            ),
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent("""\
        I will insert a comment in both files.

        @@start
        {
            "file": "multifile_calculator/calculator.py",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }
        @@code
        # Hello
        @@end
        @@start
        {
            "file": "scripts/echo.py",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }
        @@code
        # Hello
        @@end""")])

    session = await Session.create([Path("calculator.py"), Path("../scripts")])
    await session.start()
    await session.stream.stop()

    # Check that it works
    with open("calculator.py") as f:
        calculator_output = f.readlines()
    with open("../scripts/echo.py") as f:
        echo_output = f.readlines()
    assert calculator_output[0].strip() == "# Hello"
    assert echo_output[0].strip() == "# Hello"
