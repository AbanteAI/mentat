import pytest

from mentat.parsers.file_edit import FileEdit, Replacement

# Since file creation, deletion, and renaming is almost entirely handled in
# the CodeFileManager, no need to test that here


@pytest.mark.asyncio
async def test_replacement(mock_session_context):
    replacements = [
        Replacement(0, 2, ["# Line 0", "# Line 1", "# Line 2"]),
        Replacement(3, 3, ["# Inserted"]),
    ]
    file_edit = FileEdit(
        file_path=mock_session_context.cwd.joinpath("test.py"),
        replacements=replacements,
    )
    file_edit.resolve_conflicts()
    original_lines = ["# Remove me", "# Remove me", "# Line 3", "# Line 4"]
    new_lines = file_edit.get_updated_file_lines(original_lines)
    assert new_lines == [
        "# Line 0",
        "# Line 1",
        "# Line 2",
        "# Line 3",
        "# Inserted",
        "# Line 4",
    ]


# When we add user conflict resolution, this test will need to be changed
@pytest.mark.asyncio
async def test_replacement_conflict(mock_session_context):
    replacements = [
        Replacement(0, 2, ["L0"]),
        Replacement(1, 3, ["L1"]),
        Replacement(4, 7, ["L3"]),
        Replacement(5, 6, ["L2"]),
    ]
    file_edit = FileEdit(
        file_path=mock_session_context.cwd.joinpath("test.py"),
        replacements=replacements,
    )
    file_edit.resolve_conflicts()
    original_lines = ["O0", "O1", "O2", "O3", "O4", "O5", "O6"]
    new_lines = file_edit.get_updated_file_lines(original_lines)
    assert new_lines == ["L0", "L1", "O3", "L2", "L3"]
