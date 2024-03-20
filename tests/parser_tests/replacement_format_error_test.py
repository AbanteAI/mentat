from pathlib import Path
from textwrap import dedent

import pytest

from mentat.config import Config
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session import Session


@pytest.fixture(autouse=True)
def replacement_parser(mocker):
    mocker.patch.object(Config, "parser", new=ReplacementParser())


@pytest.mark.asyncio
async def test_invalid_line_numbers(
    mock_call_llm_api,
    mock_collect_user_input,
):
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
                f"""\
        Conversation

        @ {temp_file_name} insert_line=2
        # I inserted this comment
        @
        @ {temp_file_name} starting_line=-1 ending_line-2
        # I will not be used
        @
        @ {temp_file_name} insert_line=1
        # I also will not be used
        @"""
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
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
async def test_invalid_special_line(
    mock_call_llm_api,
    mock_collect_user_input,
):
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
                f"""\
        Conversation

        @ {temp_file_name} insert_line=2
        # I inserted this comment
        @
        @ {temp_file_name}
        # I will not be used
        @
        @ {temp_file_name} insert_line=1
        # I will not be used
        @"""
            )
        ]
    )

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
            # This is a temporary file
            # I inserted this comment
            # with 2 lines"""
        )
    assert content == expected_content
