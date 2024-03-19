import os
from pathlib import Path
from textwrap import dedent

from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import ParsedLLMResponse
from mentat.utils import convert_string_to_asynciter


async def verify_inverse(parser):
    cwd = Path(os.getcwd())
    parsedLLMResponse = ParsedLLMResponse(
        full_response="",
        conversation=dedent(
            """\
            Conversation
            with two lines
        """
        ),
        file_edits=[
            FileEdit(
                file_path=cwd / "test.txt",
                replacements=[
                    Replacement(
                        starting_line=1,
                        ending_line=1,
                        new_lines=["# I inserted this comment"],
                    ),
                    Replacement(starting_line=3, ending_line=4, new_lines=["# better measure"]),
                ],
                is_creation=False,
                is_deletion=False,
                rename_file_path=None,
            ),
            FileEdit(
                file_path=cwd / "delete.txt",
                replacements=[Replacement(starting_line=1, ending_line=3, new_lines=[])],
                is_creation=False,
                is_deletion=False,
                rename_file_path=None,
            ),
            FileEdit(
                file_path=cwd / "create.txt",
                replacements=[
                    Replacement(
                        starting_line=0,
                        ending_line=0,
                        new_lines=["# I created this file"],
                    )
                ],
                is_creation=True,
                is_deletion=False,
                rename_file_path=None,
            ),
            FileEdit(
                file_path=cwd / "file1.txt",
                replacements=[
                    Replacement(
                        starting_line=1,
                        ending_line=1,
                        new_lines=["# I inserted this comment in a replacement"],
                    ),
                    Replacement(
                        starting_line=3,
                        ending_line=4,
                        new_lines=["# better measure in a replacement"],
                    ),
                ],
                is_creation=False,
                is_deletion=False,
                rename_file_path=cwd / "file2.txt",
            ),
        ],
    )
    inverse = parser.file_edits_to_llm_message(parsedLLMResponse)
    generator = convert_string_to_asynciter(inverse, 10)
    back_once = await parser.stream_and_parse_llm_response(generator)
    inverse2 = parser.file_edits_to_llm_message(back_once)
    generator2 = convert_string_to_asynciter(inverse2, 10)
    back_twice = await parser.stream_and_parse_llm_response(generator2)

    # The full_response is originally blank for compatibility with all formats. So we invert twice.
    assert parsedLLMResponse.file_edits == back_once.file_edits
    assert back_once == back_twice
    # Verify the inverse uses relative paths
    assert "testbed" not in back_once.full_response
