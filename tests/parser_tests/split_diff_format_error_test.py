from textwrap import dedent

import pytest

from mentat.config import Config
from mentat.parsers.split_diff_parser import SplitDiffParser
from mentat.session import Session


@pytest.fixture(autouse=True)
def split_diff_parser(mocker):
    mocker.patch.object(Config, "parser", new=SplitDiffParser())


@pytest.mark.asyncio
async def test_no_matching_lines(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = "temp.py"
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This is
            # a temporary file
            # with
            # 4 lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation        
        
        {{fence[0]}} {temp_file_name}
        <<<<<<< HEAD
        # This doesn't
        # exist
        # with
        =======
        # I shouldn't show up
        >>>>>>> updated
        {{fence[1]}}

        {{fence[0]}} {temp_file_name}
        <<<<<<< HEAD
        # This is
        # a temporary file
        =======
        # I am 
        # a comment
        >>>>>>> updated
        {{fence[1]}}""")])

    session = Session([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # I am 
            # a comment
            # with
            # 4 lines""")
    assert content == expected_content
