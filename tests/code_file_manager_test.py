import os
from pathlib import Path
from textwrap import dedent

import pytest

from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.parsers.block_parser import BlockParser
from mentat.session import Session


# Make sure we always give posix paths to GPT
@pytest.mark.asyncio
async def test_posix_paths(mock_stream, mock_config):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = Path(os.path.join(dir_name, file_name))
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")
    code_file_manager = CodeFileManager(
        config=mock_config,
    )
    code_context = await CodeContext.create(
        config=mock_config,
        paths=[file_path],
        exclude_paths=[],
    )
    parser = BlockParser()
    code_message = await code_context.get_code_message(
        mock_config.model(), code_file_manager, parser
    )
    assert dir_name + "/" + file_name in code_message.split("\n")


@pytest.mark.asyncio
async def test_partial_files(mock_stream, mock_config):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = os.path.join(dir_name, file_name)
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write(
            dedent(
                """\
             I am a file
             with 5 lines
             third
             fourth
             fifth"""
            )
        )
    file_path_partial = file_path + ":1,3-5"

    code_file_manager = CodeFileManager(
        config=mock_config,
    )
    code_context = await CodeContext.create(
        config=mock_config,
        paths=[Path(file_path_partial)],
        exclude_paths=[],
        no_code_map=True,
    )
    parser = BlockParser()
    code_message = await code_context.get_code_message(
        mock_config.model(), code_file_manager, parser
    )
    assert code_message == dedent(
        """\
            Code Files:

            dir/file.txt
            1:I am a file
            3:third
            4:fourth
            5:fifth
              """
    )


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
    mock_call_llm_api.set_generator_values(
        [
            dedent(
                """\
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
        @@end"""
            )
        ]
    )

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
