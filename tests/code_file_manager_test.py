import os
from textwrap import dedent

from mentat.app import run
from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager


# Make sure we always give posix paths to GPT
def test_posix_paths(mock_config):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = os.path.join(dir_name, file_name)
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")
    code_file_manager = CodeFileManager(
        config=mock_config,
    )
    code_context = CodeContext(
        config=mock_config,
        paths=[file_path],
        exclude_paths=[],
    )
    code_message = code_context.get_code_message(mock_config.model(), code_file_manager)
    assert dir_name + "/" + file_name in code_message.split("\n")


def test_partial_files(mock_config):
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

    code_file_manager = CodeFileManager(
        config=mock_config,
    )
    code_context = CodeContext(
        config=mock_config,
        paths=[file_path_partial],
        exclude_paths=[],
        no_code_map=True,
    )
    code_message = code_context.get_code_message(mock_config.model(), code_file_manager)
    assert code_message == dedent("""\
            Code Files:

            dir/file.txt
            1:I am a file
            3:third
            4:fourth
            5:fifth
              """)


def test_run_from_subdirectory(
    mock_collect_user_input, mock_call_llm_api, mock_setup_api_key
):
    """Run mentat from a subdirectory of the git root"""
    # Change to the subdirectory
    os.chdir("multifile_calculator")
    mock_collect_user_input.side_effect = [
        (
            "Insert the comment # Hello on the first line of"
            " multifile_calculator/calculator.py and scripts/echo.py"
        ),
        "y",
        KeyboardInterrupt,
    ]
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

    run(["calculator.py", "../scripts"])

    # Check that it works
    with open("calculator.py") as f:
        calculator_output = f.readlines()
    with open("../scripts/echo.py") as f:
        echo_output = f.readlines()
    assert calculator_output[0].strip() == "# Hello"
    assert echo_output[0].strip() == "# Hello"
