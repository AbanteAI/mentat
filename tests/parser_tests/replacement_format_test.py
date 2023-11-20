from pathlib import Path
from textwrap import dedent

import pytest

from mentat.config import Config
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session import Session
from tests.parser_tests.inverse import verify_inverse


@pytest.fixture
def replacement_parser(mocker):
    mocker.patch.object(Config, "parser", new=ReplacementParser())


@pytest.mark.asyncio
async def test_insert(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation

        @ {temp_file_name} insert_line=2
        # I inserted this comment
        @""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # I inserted this comment
            # with 2 lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_delete(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation

        @ {temp_file_name} starting_line=1 ending_line=1
        @""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # with 2 lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_replace(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation

        @ {temp_file_name} starting_line=2 ending_line=2
        # I inserted this comment
        @""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # I inserted this comment""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_create_file(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation

        @ {temp_file_name} +
        @ {temp_file_name} insert_line=1
        # New line
        @""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # New line""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_delete_file(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation

        @ {temp_file_name} -""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    assert not Path(temp_file_name).exists()


@pytest.mark.asyncio
async def test_rename_file(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    temp_file_name_2 = "temp2.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation

        @ {temp_file_name} {temp_file_name_2}""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    assert not Path(temp_file_name).exists()
    with open(temp_file_name_2, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # with 2 lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_change_then_rename_then_change(
    mock_session_context, mock_collect_user_input, replacement_parser
):
    temp_file_name = "temp.py"
    temp_file_name_2 = "temp2.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_session_context.llm_api_handler.streamed_values = [dedent(f"""\
        Conversation
        
        @ {temp_file_name} starting_line=1 ending_line=1
        # New line 1
        @
        @ {temp_file_name} {temp_file_name_2}
        @ {temp_file_name_2} insert_line=2
        # New line 2
        @""")]

    session = Session([temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    assert not Path(temp_file_name).exists()
    with open(temp_file_name_2, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # New line 1
            # New line 2
            # with 2 lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_inverse(mock_session_context, mock_collect_user_input):
    await verify_inverse(ReplacementParser())
