from pathlib import Path
from textwrap import dedent

from mentat.config import Config
from mentat.parsers.unified_diff_parser import UnifiedDiffParser
from mentat.session import Session
from tests.conftest import pytest


@pytest.fixture(autouse=True)
def unified_diff_parser(mocker):
    mocker.patch.object(Config, "parser", new=UnifiedDiffParser())


@pytest.mark.asyncio
async def test_not_matching(
    temp_testbed,
    mock_call_llm_api,
    mock_collect_user_input,
):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
            # This is
            # a temporary file
            # with
            # 4 lines"""
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

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
         # Not matching
        -# a temporary file
        -# with
        +# your captain speaking
         # 4 lines"""
            )
        ]
    )

    session = Session(cwd=temp_testbed, paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
            # This is
            # a temporary file
            # with
            # 4 lines"""
        )
    assert content == expected_content


@pytest.mark.asyncio
async def test_no_prefix(
    temp_testbed,
    mock_call_llm_api,
    mock_collect_user_input,
):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write(
            dedent(
                """\
            # This is
            # a temporary file
            # with
            # 4 lines"""
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

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
        # This is
        -# a temporary file
        -# with
        +# your captain speaking
        # 4 lines"""
            )
        ]
    )

    session = Session(cwd=temp_testbed, paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent(
            """\
            # This is
            # a temporary file
            # with
            # 4 lines"""
        )
    assert content == expected_content
