from textwrap import dedent

import pytest

from mentat.parsers.parser import ParsedLLMResponse
from mentat.parsers.parser_map import parser_map


@pytest.mark.asyncio
async def test_parse_llm_response(mocker, temp_testbed):
    mock_file_name = temp_testbed / "multifile_calculator" / "calculator.py"
    mock_renamed_name = temp_testbed / "multifile_calculator" / "calculator_renamed.py"
    response = dedent(
        f"""\
        I will insert a comment then rename the file

        Steps:
        1. insert a comment
        2. rename the file

        @@start
        {{
            "file": "{mock_file_name.as_posix()}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # forty two
        @@end
        @@start
        {{
            "file": "{mock_file_name.as_posix()}",
            "action": "rename-file",
            "name": "{mock_renamed_name.as_posix()}"
        }}
        @@code
        @@end"""
    )

    parser = parser_map["block"]
    parsed_response = await parser.parse_llm_response(response)

    assert isinstance(parsed_response, ParsedLLMResponse)
    assert parsed_response.conversation == dedent(
        """\
        I will insert a comment then rename the file

        Steps:
        1. insert a comment
        2. rename the file
        
        """
    )
    assert "forty two" in parsed_response.full_response
    assert "forty two" not in parsed_response.conversation
    assert len(parsed_response.file_edits) == 1
    file_edit = parsed_response.file_edits[0]
    assert file_edit.rename_file_path == mock_renamed_name
