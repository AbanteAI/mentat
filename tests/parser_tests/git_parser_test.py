import os
import re
from textwrap import dedent

import pytest
from git import Repo

from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.git_parser import GitParser
from mentat.parsers.parser import ParsedLLMResponse
from mentat.utils import convert_string_to_asynciter


def clean_diff(diff):
    """
    NOTE: Git diffs include SHA-1 hashes, which links the diff to a known record
    in the git repo. We won't have that, so diffs generated with this function cannot be
    applied via `git apply myfile.diff`.
    """
    diff = re.sub(r"\bindex \b[0-9a-f]{5,40}\b.*", "", diff)  # Remove hexshas
    diff = re.sub(r"(@@ [^@]* @@).*", r"\1", diff)  # Remove context from hunk_headers
    return diff


@pytest.fixture
def create_file_edit(temp_testbed):
    return FileEdit(
        file_path=temp_testbed / "create.txt",
        replacements=[
            Replacement(
                starting_line=0,
                ending_line=0,
                new_lines=["# I created this file", "# And it has two lines"],
            )
        ],
        is_creation=True,
    )


@pytest.fixture
def delete_file_edit(temp_testbed, mock_session_context):
    file_to_delete = temp_testbed / "format_examples" / "replacement.txt"
    previous_file_lines = mock_session_context.code_file_manager.read_file(file_to_delete)
    return FileEdit(
        file_path=file_to_delete,
        replacements=[],
        is_deletion=True,
        previous_file_lines=previous_file_lines,
    )


@pytest.fixture
def rename_file_edit(temp_testbed, mock_session_context):
    file_to_rename = temp_testbed / "scripts" / "echo.py"
    cfm = mock_session_context.code_file_manager
    rename_to = temp_testbed / "scripts" / "echo2.py"
    return FileEdit(
        file_path=file_to_rename,
        rename_file_path=rename_to,
        previous_file_lines=cfm.read_file(file_to_rename),
    )


@pytest.fixture
def modify_file_edit(temp_testbed, mock_session_context):
    file_to_modify = temp_testbed / "multifile_calculator" / "operations.py"
    previous_file_lines = mock_session_context.code_file_manager.read_file(file_to_modify)
    return FileEdit(
        file_path=file_to_modify,
        replacements=[
            Replacement(starting_line=0, ending_line=1, new_lines=[]),  # Remove a line
            Replacement(
                starting_line=4,
                ending_line=5,
                new_lines=["def multiply_numbers(a, b): # I modified this line"],
            ),
            Replacement(starting_line=14, ending_line=14, new_lines=["# I added this line"]),
        ],
        previous_file_lines=previous_file_lines,
    )


def test_creation_file_edit_to_git_diff(temp_testbed, create_file_edit):
    repo = Repo(temp_testbed)

    add_file_diff = GitParser().file_edit_to_git_diff(create_file_edit)

    with open(temp_testbed / "create.txt", "w") as f:
        f.write("# I created this file\n# And it has two lines\n")
    repo.git.add(["--all"])
    expected_diff = repo.git.diff(["--staged"], unified=0)

    assert clean_diff(add_file_diff) == clean_diff(expected_diff)
    # TODO: Test with one or multiple lines


def test_deletion_file_edit_to_git_diff(temp_testbed, delete_file_edit):
    repo = Repo(temp_testbed)

    delete_file_diff = GitParser().file_edit_to_git_diff(delete_file_edit)

    file_to_delete = delete_file_edit.file_path
    file_to_delete.unlink()
    repo.git.add(["--all"])
    expected_diff = repo.git.diff(["--staged"], unified=0)

    assert not file_to_delete.exists()
    assert clean_diff(expected_diff) == clean_diff(delete_file_diff)


def test_rename_file_edit_to_git_diff(temp_testbed, rename_file_edit):
    repo = Repo(temp_testbed)

    rename_file_diff = GitParser().file_edit_to_git_diff(rename_file_edit)

    os.rename(rename_file_edit.file_path, rename_file_edit.rename_file_path)
    repo.git.add(["--all"])
    expected_diff = repo.git.diff(["--staged"], unified=0)

    assert clean_diff(rename_file_diff) == clean_diff(expected_diff)
    # TODO: Test with and without edits


def test_modify_file_edit_to_git_diff(temp_testbed, modify_file_edit):
    repo = Repo(temp_testbed)

    modify_file_diff = GitParser().file_edit_to_git_diff(modify_file_edit)

    with open(modify_file_edit.file_path, "w") as f:
        f.write(
            dedent(
                """\
            return a + b


        def multiply_numbers(a, b): # I modified this line
            return a * b


        def subtract_numbers(a, b):
            return a - b


        def divide_numbers(a, b):
            return a / b
        # I added this line
        """
            )
        )
    repo.git.add(["--all"])
    expected_diff = repo.git.diff(["--staged"], unified=0)

    assert clean_diff(modify_file_diff) == clean_diff(expected_diff)


@pytest.mark.asyncio
async def test_git_parser_inverse(temp_testbed, create_file_edit, delete_file_edit, rename_file_edit, modify_file_edit):
    """
    This is mostly a duplicate of inverse.py, but the git_parser needs the removed/previous
    lines so I use actual files instead.
    """
    parsedLLMResponse = ParsedLLMResponse(
        full_response="",
        conversation=dedent(
            """\
            Conversation
            with two lines
        """
        ),
        file_edits=[
            create_file_edit,
            delete_file_edit,
            rename_file_edit,
            modify_file_edit,
        ],
    )

    parser = GitParser()

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
