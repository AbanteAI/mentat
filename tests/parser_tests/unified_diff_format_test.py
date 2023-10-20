from pathlib import Path
from textwrap import dedent

import pytest

from mentat.config_manager import ConfigManager
from mentat.session import Session


@pytest.fixture(autouse=True)
def unified_diff_parser(mocker):
    mock_method = mocker.MagicMock()
    mocker.patch.object(ConfigManager, "parser", new=mock_method)
    mock_method.return_value = "unified-diff"


@pytest.mark.asyncio
async def test_replacement(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = Path("temp.py")
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

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
         # This is
        -# a temporary file
        -# with
        +# your captain speaking
         # 4 lines
        @@ end @@""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is
            # your captain speaking
            # 4 lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_multiple_replacements(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This
            # is
            # a
            # temporary
            # file
            # with
            # 8
            # lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
         # This
        -# is
        +# was
         # a
         # temporary
        +# extra line
         # file
        -# with
        -# 8
        +# new line
         # lines
        @@ end @@""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This
            # was
            # a
            # temporary
            # extra line
            # file
            # new line
            # lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_multiple_replacement_spots(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This
            # is
            # a
            # temporary
            # file
            # with
            # 8
            # lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
        -# is
        +# was
        @@ @@
        -# file
         # with
        +# more than
        @@ end @@""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This
            # was
            # a
            # temporary
            # with
            # more than
            # 8
            # lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_little_context_addition(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This
            # is
            # a
            # temporary
            # file
            # with
            # 8
            # lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
         # is
        +# New line
        @@ @@
        +# New line 2
         # with 
        @@ end @@""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This
            # is
            # New line
            # a
            # temporary
            # file
            # New line 2
            # with
            # 8
            # lines""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_empty_file(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write("")

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
        +# New
        +# line
        @@ end @@""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # New
            # line
            """)
    assert content == expected_content


@pytest.mark.asyncio
async def test_creation(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    temp_file_name = Path("temp.py")

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation

        --- /dev/null
        +++ {temp_file_name}
        @@ @@
        +# New line
        @@ end @@
        """)])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # New line""")
    assert content == expected_content


@pytest.mark.asyncio
async def test_deletion(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    temp_file_name = Path("temp.py")
    with open(temp_file_name, "w") as f:
        f.write(dedent("""\
            # This
            # is
            # a
            # temporary
            # file
            # with
            # 8
            # lines"""))

    mock_collect_user_input.set_stream_messages(
        [
            "test",
            "y",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_generator_values([dedent(f"""\
        Conversation

        --- {temp_file_name}
        +++ /dev/null
        @@ end @@""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    assert not temp_file_name.exists()


@pytest.mark.asyncio
async def test_no_ending_marker(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    temp_file_name = Path("temp.py")
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

        --- {temp_file_name}
        +++ {temp_file_name}
        @@ @@
         # This is
        -# a temporary file
        -# with
        +# your captain speaking
         # 4 lines""")])

    session = await Session.create([temp_file_name])
    await session.start()
    session.stream.stop()
    with open(temp_file_name, "r") as f:
        content = f.read()
        expected_content = dedent("""\
            # This is
            # your captain speaking
            # 4 lines""")
    assert content == expected_content
