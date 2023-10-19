from textwrap import dedent

import pytest

from mentat.session import Session
from tests.conftest import ConfigManager


@pytest.fixture(autouse=True)
def replacement_parser(mocker):
    mock_method = mocker.MagicMock()
    mocker.patch.object(ConfigManager, "parser", new=mock_method)
    mock_method.return_value = "replacement"


@pytest.mark.asyncio
async def test_invalid_line_numbers(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
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
    mock_call_llm_api.set_generator_values([dedent(f"""\
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

    session = await Session.create([temp_file_name])
    await session.start()
    await session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # I inserted this comment
            # with 2 lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_invalid_special_line(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
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
    mock_call_llm_api.set_generator_values([dedent(f"""\
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

    session = await Session.create([temp_file_name])
    await session.start()
    await session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is a temporary file
            # I inserted this comment
            # with 2 lines""")
    assert content == expected_content
