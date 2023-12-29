from pathlib import Path
from textwrap import dedent

import pytest

import mentat
from mentat.config import ParserSettings
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session import Session
from mentat.utils import dd


@pytest.fixture(autouse=True)
def replacement_parser(mocker):
    mocker.patch.object(ParserSettings, "parser", new=ReplacementParser())


@pytest.mark.asyncio
async def test_invalid_line_numbers(
    mock_call_llm_api,
    mock_collect_user_input,
):
    temp_file_name = "temp.py"
    temp_file_location = Path.cwd() / temp_file_name

    config = mentat.user_session.get("config")
    config.parser.parser = ReplacementParser()
    mentat.user_session.set("config", config)

    with open(temp_file_location, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages([
        "test",
        "y",
        "q",
    ])
    mock_call_llm_api.set_streamed_values([dedent(f"""\
        Conversation

        @ {temp_file_name} insert_line=2
        # I inserted this comment
        @
        @ {temp_file_name} starting_line=-1 ending_line-2
        # I will not be used
        @
        @ {temp_file_name} insert_line=1
        # I also will not be used
        @""")])

    session = Session(cwd=Path.cwd(), paths=[Path(temp_file_location)])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_location, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # I inserted this comment
            # with 2 lines""")

    assert content == expected_content


@pytest.mark.asyncio
async def test_invalid_special_line(
    mock_call_llm_api,
    mock_collect_user_input,
):
    config = mentat.user_session.get("config")
    config.parser.parser = ReplacementParser()
    mentat.user_session.set("config", config)

    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is a temporary file
            # with 2 lines"""))

    mock_collect_user_input.set_stream_messages([
        "test",
        "y",
        "q",
    ])
    mock_call_llm_api.set_streamed_values([dedent(f"""\
        Conversation

        @ {temp_file_name} insert_line=2
        # I inserted this comment
        @
        @ {temp_file_name}
        # I will not be used
        @
        @ {temp_file_name} insert_line=1
        # I will not be used
        @""")])

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # I inserted this comment
            # with 2 lines""")
    assert content == expected_content
