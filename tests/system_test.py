import os
from textwrap import dedent

from mentat.app import run


def test_system(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write("# This is a temporary file.")

    mock_collect_user_input.side_effect = [
        'Replace comment with print("Hello, world!")',
        "y",
        KeyboardInterrupt,
    ]
    mock_call_llm_api.set_generator_values([dedent("""\
        I will add a print statement.

        Steps:
        1. Add a print statement after the last line

        @@start
        {{
            "file": "{file_name}",
            "action": "replace",
            "start-line": 1,
            "end-line": 1
        }}
        @@code
        print("Hello, world!")
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = 'print("Hello, world!")'
    assert content == expected_content


def test_interactive_change_selection(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    # Create a temporary file
    temp_file_name = "temp_interactive.py"
    with open(temp_file_name, "w") as f:
        f.write("# This is a temporary file for interactive test.")

    mock_collect_user_input.side_effect = [
        "Add changes to the file",
        "i",
        "y",
        "n",
        "y",
        KeyboardInterrupt,
    ]
    mock_call_llm_api.set_generator_values([dedent("""\
        I will make three changes to the file.

        Steps:
        1. Replace the comment with print("Change 1")
        2. Add print("Change 2") after the first line
        3. Add print("Change 3") after the second line

        @@start
        {{
            "file": "{file_name}",
            "action": "replace",
            "start-line": 1,
            "end-line": 1
        }}
        @@code
        print("Change 1")
        @@end
        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-after-line": 1,
            "insert-before-line": 2
        }}
        @@code
        print("Change 2")
        @@end
        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-after-line": 2,
            "insert-before-line": 3
        }}
        @@code
        print("Change 3")
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = 'print("Change 1")\n\nprint("Change 3")'
    assert content == expected_content


# Makes sure we're properly turning the model output into correct path no matter the os
def test_without_os_join(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_dir = "dir"
    temp_file_name = "temp.py"
    temp_file_path = os.path.join(temp_dir, temp_file_name)
    os.makedirs(temp_dir, exist_ok=True)
    with open(temp_file_path, "w") as f:
        f.write("# This is a temporary file.")

    mock_collect_user_input.side_effect = [
        'Replace comment with print("Hello, world!")',
        "y",
        KeyboardInterrupt,
    ]

    # Use / here since that should always be what the model outputs
    fake_file_path = temp_dir + "/" + temp_file_name
    mock_call_llm_api.set_generator_values([dedent("""\
        I will add a print statement.

        Steps:
        1. Add a print statement after the last line

        @@start
        {{
            "file": "{file_name}",
            "action": "replace",
            "start-line": 1,
            "end-line": 1
        }}
        @@code
        print("Hello, world!")
        @@end""".format(file_name=fake_file_path))])

    run([temp_file_path])
    with open(temp_file_path, "r") as f:
        content = f.read()
        expected_content = 'print("Hello, world!")'
    assert content == expected_content
