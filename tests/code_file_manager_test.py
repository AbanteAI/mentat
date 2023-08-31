import os
from textwrap import dedent

from mentat.code_context import CodeContext
from mentat.code_file_manager import CodeFileManager
from mentat.user_input_manager import UserInputManager


# Make sure we always give posix paths to GPT
def test_posix_paths(mock_config):
    dir_name = "dir"
    file_name = "file.txt"
    file_path = os.path.join(dir_name, file_name)
    os.makedirs(dir_name, exist_ok=True)
    with open(file_path, "w") as file_file:
        file_file.write("I am a file")
    code_context = CodeContext(
        config=mock_config,
        paths=[file_path],
        exclude_paths=[],
    )
    code_file_manager = CodeFileManager(
        user_input_manager=UserInputManager(
            config=mock_config, code_context=code_context
        ),
        config=mock_config,
        code_context=code_context,
    )
    code_message = code_file_manager.get_code_message()
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

    code_context = CodeContext(
        config=mock_config,
        paths=[file_path_partial],
        exclude_paths=[],
    )
    code_file_manager = CodeFileManager(
        user_input_manager=UserInputManager(
            config=mock_config, code_context=code_context
        ),
        config=mock_config,
        code_context=code_context,
    )
    code_message = code_file_manager.get_code_message()
    assert code_message == dedent("""\
             Code Files:

             dir/file.txt
             1:I am a file
             3:third
             4:fourth
             5:fifth
              """)
