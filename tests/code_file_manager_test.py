import os
from pathlib import Path
from textwrap import dedent

import pytest

from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.session import Session


# Make sure we always give posix paths to GPT
@pytest.mark.asyncio
async def test_posix_paths(mock_session_context):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = Path(os.path.join(dir_name, file_name))
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")
    mock_session_context.code_context.include(file_path)

    code_message = await mock_session_context.code_context.get_code_message(0)
    assert any(line.startswith(dir_name + "/" + file_name) for line in code_message.split("\n"))


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_partial_files(mocker, mock_session_context):
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

    file_path_partial = Path(file_path + ":1,3-5")
    mock_session_context.code_context.include(file_path_partial)
    mock_session_context.code_context.code_map = False

    code_message = await mock_session_context.code_context.get_code_message(0)
    assert code_message == dedent(
        """\
            Code Files:

            dir/file.txt
            1:I am a file
            ...
            3:third
            4:fourth
            ...
            """
    )


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_run_from_subdirectory(
    temp_testbed,
    mock_collect_user_input,
    mock_call_llm_api,
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
    mock_call_llm_api.set_streamed_values(
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

    session = Session(cwd=temp_testbed, paths=["multifile_calculator/calculator.py", "scripts"])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check that it works
    with open("calculator.py") as f:
        calculator_output = f.readlines()
    with open("../scripts/echo.py") as f:
        echo_output = f.readlines()
    assert calculator_output[0].strip() == "# Hello"
    assert echo_output[0].strip() == "# Hello"


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_run_from_superdirectory(
    temp_testbed,
    mock_collect_user_input,
    mock_call_llm_api,
):
    """Run mentat from outside the git root"""
    # Change to the subdirectory
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
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
        I will insert a comment in both files.

        @@start
        {
            "file": "../multifile_calculator/calculator.py",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }
        @@code
        # Hello
        @@end
        @@start
        {
            "file": "../scripts/echo.py",
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

    session = Session(
        cwd=Path(temp_testbed) / "format_examples",
        paths=["../multifile_calculator/calculator.py", "../scripts"],
    )
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check that it works
    with open("multifile_calculator/calculator.py") as f:
        calculator_output = f.readlines()
    with open("scripts/echo.py") as f:
        echo_output = f.readlines()
    assert calculator_output[0].strip() == "# Hello"
    assert echo_output[0].strip() == "# Hello"


@pytest.mark.ragdaemon
@pytest.mark.asyncio
async def test_change_after_creation(
    mock_collect_user_input,
    mock_call_llm_api,
):
    file_name = Path("hello_world.py")
    mock_collect_user_input.set_stream_messages(
        [
            "Conversation",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                f"""\
        Conversation

        @@start
        {{
            "file": "{file_name}",
            "action": "create-file"
        }}
        @@code
        @@end
        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        print("Hello, World!")
        @@end"""
            )
        ]
    )

    session = Session(cwd=Path.cwd())
    session.start()
    await session.stream.recv(channel="client_exit")

    with file_name.open() as f:
        output = f.read()
    assert output == 'print("Hello, World!")'


@pytest.mark.asyncio
@pytest.mark.no_git_testbed
async def test_changed_file(
    mocker,
    temp_testbed,
    mock_collect_user_input,
    mock_session_context,
):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = Path(temp_testbed) / dir_name / file_name
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")

    code_context = mock_session_context.code_context
    code_context.include(file_path)

    # Load code_file_manager's file_lines
    code_file_manager = mock_session_context.code_file_manager
    code_file_manager.read_file(file_path)

    # Update the included files
    with open(file_path, "w") as file_file:
        file_file.write("I was a file")

    # Try to write_changes
    file_edit = FileEdit(
        file_path=file_path,
        replacements=[Replacement(0, 1, ["I am a file", "with edited lines"])],
    )
    assert file_edit.is_valid()

    # Decline overwrite
    mock_collect_user_input.set_stream_messages(["n", "q"])
    await code_file_manager.write_changes_to_files([file_edit])
    assert file_path.read_text().splitlines() == ["I was a file"]

    # Accept overwrite
    mock_collect_user_input.set_stream_messages(["y", "q"])
    await code_file_manager.write_changes_to_files([file_edit])
    assert file_path.read_text().splitlines() == ["I am a file", "with edited lines"]
