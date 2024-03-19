import os
from pathlib import Path
from textwrap import dedent

import pytest

from mentat.config import Config
from mentat.parsers.block_parser import BlockParser
from mentat.session import Session
from tests.parser_tests.inverse import verify_inverse


@pytest.fixture
def block_parser(mocker):
    mocker.patch.object(Config, "parser", new=BlockParser())


@pytest.mark.asyncio
async def test_insert(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
                        # This is a temporary file
                        # with 2 lines"""
            )
        )

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
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
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    # Run the system with the temporary file path
    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
                        # This is a temporary file
                        # I inserted this comment
                        # with 2 lines"""
        )
    assert content == expected_content


@pytest.mark.asyncio
async def test_replace(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
                        # This is a temporary file
                        # with 2 lines"""
            )
        )

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
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
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    # Run the system with the temporary file path
    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
                        # I inserted this comment"""
        )
    assert content == expected_content


@pytest.mark.asyncio
async def test_delete(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
                        # This is a temporary
                        # file
                        # with 4 
                        # lines"""
            )
        )

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
        I will delete the middle two lines

        Steps: 1. Delete the middle two lines

        @@start
        {{
            "file": "{file_name}",
            "action": "delete",
            "start-line": 2,
            "end-line": 3
        }}
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    # Run the system with the temporary file path
    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
                        # This is a temporary
                        # lines"""
        )
    assert content == expected_content


@pytest.mark.asyncio
async def test_create_file(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Create a temporary file
    temp_file_name = "new_dir/temp.py"
    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
        I will create a new file called temp.py

        Steps: 1. Create a new file called temp.py

        @@start
        {{
            "file": "{file_name}",
            "action": "create-file"
        }}
        @@code
        # I created this file
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=["."])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
                        # I created this file"""
        )
    assert content == expected_content


@pytest.mark.asyncio
async def test_delete_file(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Create a temporary file
    temp_file_name = "incredibly_temp.py"
    with open(temp_file_name, "w") as f:
        f.write("# I am not long for this world")

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
        I will delete the file

        Steps: 1. Delete the file

        @@start
        {{
            "file": "{file_name}",
            "action": "delete-file"
        }}
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    # Run the system with the temporary file path
    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    assert not os.path.exists(temp_file_name)


@pytest.mark.asyncio
async def test_rename_file(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Make sure rename-file works
    temp_file_name = "temp.py"
    temp_2_file_name = "temp_2.py"
    with open(temp_file_name, "w") as f:
        f.write("# Move me!")

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                f"""\
        I will rename the file

        Steps: 1. rename the file

        @@start
        {{
            "file": "{temp_file_name}",
            "action": "rename-file",
            "name": "{temp_2_file_name}"
        }}
        @@end"""
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_2_file_name) as new_file:
        content = new_file.read()
        expected_content = "# Move me!"

    assert not os.path.exists(temp_file_name)
    assert content == expected_content


@pytest.mark.asyncio
async def test_change_then_rename_file(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Make sure a change made before a rename works
    temp_file_name = "temp.py"
    temp_2_file_name = "temp_2.py"
    with open(temp_file_name, "w") as f:
        f.write("# Move me!")

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                f"""\
        I will insert a comment then rename the file

        Steps:
        1. insert a comment
        2. rename the file

        @@start
        {{
            "file": "{temp_file_name}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # I inserted this comment!
        @@end
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "rename-file",
            "name": "{temp_2_file_name}"
        }}
        @@end"""
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_2_file_name) as new_file:
        content = new_file.read()
        expected_content = "# I inserted this comment!\n# Move me!"

    assert not os.path.exists(temp_file_name)
    assert content == expected_content


@pytest.mark.asyncio
async def test_rename_file_then_change(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Make sure a change made after a rename works
    temp_file_name = "temp.py"
    temp_2_file_name = "temp_2.py"
    with open(temp_file_name, "w") as f:
        f.write("# Move me!")

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                f"""\
        I will rename the file then insert a comment

        Steps:
        1. rename the file
        2. insert a comment

        @@start
        {{
            "file": "{temp_file_name}",
            "action": "rename-file",
            "name": "{temp_2_file_name}"
        }}
        @@end
        @@start
        {{
            "file": "{temp_2_file_name}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # I inserted this comment!
        @@end"""
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_2_file_name) as new_file:
        content = new_file.read()
        expected_content = "# I inserted this comment!\n# Move me!"

    assert not os.path.exists(temp_file_name)
    assert content == expected_content


@pytest.mark.asyncio
async def test_multiple_blocks(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Create a temporary file
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
                        # This is a temporary file
                        # with 4 lines
                        # just for
                        # good measure"""
            )
        )

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
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
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    # Run the system with the temporary file path
    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
                        # This is a temporary file
                        # I inserted this comment
                        # with 4 lines
                        # just for
                        # better measure"""
        )
    assert content == expected_content


@pytest.mark.asyncio
async def test_inverse(mock_call_llm_api, mock_collect_user_input):
    await verify_inverse(BlockParser())


@pytest.mark.asyncio
async def test_json_strings(mock_call_llm_api, mock_collect_user_input, block_parser):
    # Make sure we don't throw error if GPT gives us numbers in a string format
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
            # This is a temporary file"""
            )
        )

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )

    mock_call_llm_api.set_streamed_values(
        [
            dedent(
                """\
        I will insert a comment at the start.

        @@start
        {{
            "file": "{file_name}",
            "action": "insert",
            "insert-after-line": "0",
            "insert-before-line": "1"
        }}
        @@code
        # I inserted this comment
        @@end
        @@start
        {{
            "file": "{file_name}",
            "action": "replace",
            "start-line": "1",
            "end-line": "1"
        }}
        @@code
        # I replaced this comment
        @@end""".format(file_name=temp_file_name)
            )
        ]
    )

    # Run the system with the temporary file path
    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")

    # Check if the temporary file is modified as expected
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
            # I inserted this comment
            # I replaced this comment"""
        )
    assert content == expected_content
