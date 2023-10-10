import os
from pathlib import Path
from textwrap import dedent

import pytest

from mentat.code_file_manager import CODE_FILE_MANAGER, CodeFileManager
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.session import Session


# Make sure we always give posix paths to GPT
@pytest.mark.asyncio
async def test_posix_paths(
    mock_stream, mock_config, mock_code_file_manager, mock_code_context, mock_parser
):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = Path(os.path.join(dir_name, file_name))
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")

    mock_code_context.settings.paths = [file_path]
    mock_code_context._set_include_files()

    code_message = await mock_code_context.get_code_message(mock_config.model(), 1e6)
    assert dir_name + "/" + file_name in code_message.split("\n")


@pytest.mark.asyncio
async def test_partial_files(
    mock_stream, mock_config, mock_code_file_manager, mock_code_context, mock_parser
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
    mock_code_context.settings.auto_tokens = 0
    mock_code_context._set_include_files()
    mock_code_context.code_map = False

    code_message = await mock_code_context.get_code_message(
        mock_config.model(), max_tokens=1e6
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

    session = await Session.create(
        [Path("calculator.py"), Path("../scripts")], auto_tokens=0
    )
    await session.start()
    await session.stream.stop()

    # Check that it works
    with open("calculator.py") as f:
        calculator_output = f.readlines()
    with open("../scripts/echo.py") as f:
        echo_output = f.readlines()
    assert calculator_output[0].strip() == "# Hello"
    assert echo_output[0].strip() == "# Hello"


@pytest.mark.asyncio
async def test_changed_file(
    mocker,
    temp_testbed,
    mock_stream,
    mock_config,
    mock_collect_user_input,
    mock_code_context,
    mock_parser,
):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = Path(temp_testbed) / dir_name / file_name
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")
    mock_code_context.settings.paths = [file_path]
    mock_code_context._set_include_files()

    # Load code_file_manager's file_lines
    code_file_manager = CodeFileManager()
    CODE_FILE_MANAGER.set(code_file_manager)
    code_file_manager.read_file(file_path)

    # Update the included files
    with open(file_path, "w") as file_file:
        file_file.write("I was a file")

    # Try to write_changes
    file_edit = FileEdit(
        file_path=file_path,
        replacements=[Replacement(0, 1, ["I am a file", "with edited lines"])],
    )
    assert await file_edit.is_valid()

    # Decline overwrite
    mock_collect_user_input.set_stream_messages(["n", "q"])
    await code_file_manager.write_changes_to_files([file_edit], mock_code_context)
    assert file_path.read_text().splitlines() == ["I was a file"]

    # Accept overwrite
    mock_collect_user_input.set_stream_messages(["y", "q"])
    await code_file_manager.write_changes_to_files([file_edit], mock_code_context)
    assert file_path.read_text().splitlines() == ["I am a file", "with edited lines"]
