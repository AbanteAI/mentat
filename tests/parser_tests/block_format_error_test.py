from pathlib import Path
from textwrap import dedent

import pytest

from mentat.config import Config
from mentat.parsers.block_parser import BlockParser
from mentat.session import Session


@pytest.fixture(autouse=True)
def block_parser(mocker):
    mocker.patch.object(Config, "parser", new=BlockParser())


temp_file_name = "temp.py"
template_insert_content = "# I inserted this comment"
template_insert_expected_content = template_insert_content + "\n"
template_double_insert_expected_content = template_insert_content + "\n\n" + template_insert_content
template_insert = dedent(
    f"""\
    @@start
    {{
        "file": "{temp_file_name}",
        "action": "insert",
        "insert-after-line": 0,
        "insert-before-line": 1
    }}
    @@code
    {template_insert_content}
    @@end
    """
)
template_insert2 = dedent(
    f"""\
    @@start
    {{
        "file": "{temp_file_name}",
        "action": "insert",
        "insert-after-line": 1,
        "insert-before-line": 2
    }}
    @@code
    {template_insert_content}
    @@end
    """
)


async def error_test_template(
    mock_call_llm_api,
    mock_collect_user_input,
    changes,
):
    # Automatically set everything up given and use given changes
    with open(temp_file_name, "w") as f:
        f.write("")

    mock_collect_user_input.set_stream_messages(
        [
            "Go!",
            "y",
            "q",
        ]
    )
    mock_call_llm_api.set_streamed_values([changes])

    session = Session(cwd=Path.cwd(), paths=[temp_file_name])
    session.start()
    await session.stream.recv(channel="client_exit")
    with open(temp_file_name, "r") as f:
        content = f.read()
    return content


# These tests should not accept any changes after the invalid one
@pytest.mark.asyncio
async def test_malformed_json(
    mock_call_llm_api,
    mock_collect_user_input,
):
    # Should stop and only allow applying changes up to that point, not including malformed change
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            """\
        @@start
        {{
            "malformed-json: [,
        }}
        @@code
        # My json is malformed :(
        @@end
        """
        )
        + template_insert2,
    )
    assert content == template_insert_expected_content


@pytest.mark.asyncio
async def test_unknown_action(
    mock_call_llm_api,
    mock_collect_user_input,
):
    # Should stop and only allow applying changes up to that point, not including unknown action change
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "unknown",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # I am unknown
        @@end
        """
        )
        + template_insert2,
    )
    assert content == template_insert_expected_content


@pytest.mark.asyncio
async def test_no_line_numbers(
    mock_call_llm_api,
    mock_collect_user_input,
):
    # Should have line numbers
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "replace"
        }}
        @@code
        # I have no line numbers
        @@end
        """
        )
        + template_insert2,
    )
    assert content == template_insert_expected_content


@pytest.mark.asyncio
async def test_invalid_line_numbers(
    mock_call_llm_api,
    mock_collect_user_input,
):
    # First line number should be <= the last line number
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "replace",
            "start-line": 10,
            "end-line": 4
        }}
        @@code
        # I have wrong line numbers
        @@end
        """
        )
        + template_insert2,
    )
    assert content == template_insert_expected_content


@pytest.mark.asyncio
async def test_existing_file(
    mock_call_llm_api,
    mock_collect_user_input,
):
    # Creating file that already exists should fail
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "create-file"
        }}
        @@code
        # I already exist
        @@end
        """
        )
        + template_insert2,
    )
    assert content == ""


@pytest.mark.asyncio
async def test_file_not_in_context(
    mock_call_llm_api,
    mock_collect_user_input,
):
    with open("iamnotincontext", "w") as f:
        f.write("")
    # Trying to access file not in context should fail
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            """\
        @@start
        {
            "file": "iamnotincontext",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }
        @@code
        # I am not in context
        @@end
        """
        )
        + template_insert2,
    )
    assert content == template_double_insert_expected_content


@pytest.mark.asyncio
async def test_rename_file_already_exists(
    mock_call_llm_api,
    mock_collect_user_input,
):
    # Trying to rename to existing file shouldn't work
    existing_file_name = "existing.py"
    with open(existing_file_name, "w") as existing_file:
        existing_file.write("I was always here")
    content = await error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        template_insert
        + dedent(
            f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "rename-file",
            "name": "{existing_file_name}"
        }}
        @@end
        """
        )
        + template_insert2,
    )
    assert content == template_double_insert_expected_content
