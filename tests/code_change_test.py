import os
from textwrap import dedent

from mentat.app import run


def test_insert(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
                        # This is a temporary file
                        # with 2 lines"""))

    mock_collect_user_input.side_effect = [
        "Insert a comment between both lines",
        "y",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent("""\
        I will insert a comment between both lines.

        Steps: 1. Insert a comment after the first line

        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-after-line": 1,
            "insert-before-line": 2
        }}
        @@code
        # I inserted this comment
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
                        # This is a temporary file
                        # I inserted this comment
                        # with 2 lines""")
    assert content == expected_content


def test_replace(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
                        # This is a temporary file
                        # with 2 lines"""))

    mock_collect_user_input.side_effect = [
        "Replace both lines with one comment",
        "y",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent("""\
        I will replace both lines with one comment

        Steps: 1. Replace both lines with one comment

        @@start
        {{
            "file": "{file_name}",
            "action": "replace",
            "start-line": 1,
            "end-line": 2
        }}
        @@code
        # I inserted this comment
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
                        # I inserted this comment""")
    assert content == expected_content


def test_delete(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
                        # This is a temporary
                        # file
                        # with 4 
                        # lines"""))

    mock_collect_user_input.side_effect = [
        "Delete the middle two lines",
        "y",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent("""\
        I will delete the middle two lines

        Steps: 1. Delete the middle two lines

        @@start
        {{
            "file": "{file_name}",
            "action": "delete",
            "start-line": 2,
            "end-line": 3
        }}
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
                        # This is a temporary
                        # lines""")
    assert content == expected_content


def test_create_file(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Create a temporary file
    temp_file_name = "new_dir/temp.py"
    mock_collect_user_input.side_effect = [
        "Create a new file called temp.py",
        "y",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent("""\
        I will create a new file called temp.py

        Steps: 1. Create a new file called temp.py

        @@start
        {{
            "file": "{file_name}",
            "action": "create-file"
        }}
        @@code
        # I created this file
        @@end""".format(file_name=temp_file_name))])

    run(["."])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
                        # I created this file""")
    print(content)
    print(expected_content)
    assert content == expected_content


def test_delete_file(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Create a temporary file
    temp_file_name = "incredibly_temp.py"
    with open(temp_file_name, "w") as f:
        f.write("# I am not long for this world")

    mock_collect_user_input.side_effect = [
        "Delete the file",
        "y",
        "y",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent("""\
        I will delete the file

        Steps: 1. Delete the file

        @@start
        {{
            "file": "{file_name}",
            "action": "delete-file"
        }}
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    assert not os.path.exists(temp_file_name)


def test_multiple_blocks(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
                        # This is a temporary file
                        # with 4 lines
                        # just for
                        # good measure"""))

    mock_collect_user_input.side_effect = [
        (
            "Insert a comment between the first 2 lines and then replace the last line"
            " with 'better measure'"
        ),
        "y",
        KeyboardInterrupt,
    ]

    mock_call_llm_api.set_generator_values([dedent("""\
        I will insert a comment between the first two lines
        and then replace the last line with 'better measure'

        Steps: 1. Insert a comment
               2. Replace last line

        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-after-line": 1,
            "insert-before-line": 2
        }}
        @@code
        # I inserted this comment
        @@end
        @@start
        {{
            "file": "{file_name}",
            "action": "replace",
            "start-line": 4,
            "end-line": 4
        }}
        @@code
        # better measure
        @@end""".format(file_name=temp_file_name))])

    # Run the system with the temporary file path
    run([temp_file_name])

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
                        # This is a temporary file
                        # I inserted this comment
                        # with 4 lines
                        # just for
                        # better measure""")
    assert content == expected_content
