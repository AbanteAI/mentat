from pathlib import Path

from mentat.code_changes.abstract.abstract_change import (
    AbstractChange,
    Addition,
    Deletion,
    FileUpdate,
)


def test_additions(temp_testbed, mock_context, mock_user_input_manager):
    # Test that multiple on additions on same and different lines works
    file_path = Path("test.py")
    change = AbstractChange(
        file_path,
        [
            Addition(1, ["I end up on line 3"], 0),
            Addition(0, ["I end up on line 0"], 0),
            Addition(1, ["I end up on line 2"], 0),
        ],
    )
    code_lines = ["Line 0", "Line 1", "Line 2"]
    new_code_lines = change.apply(code_lines, mock_context, mock_user_input_manager)
    assert new_code_lines == [
        "I end up on line 0",
        "Line 0",
        "I end up on line 2",
        "I end up on line 3",
        "Line 1",
        "Line 2",
    ]


def test_deletions(temp_testbed, mock_context, mock_user_input_manager):
    # Test that multiple deletions delete the correct lines
    file_path = Path("test.py")
    change = AbstractChange(
        file_path,
        [Deletion(1, 3, 0), Deletion(4, 5, 0)],
    )
    code_lines = ["Line 0", "Line 1", "Line 2", "Line 3", "Line 4", "Line 5"]
    new_code_lines = change.apply(code_lines, mock_context, mock_user_input_manager)
    assert new_code_lines == ["Line 0", "Line 3", "Line 5"]


def test_overlap(temp_testbed, mock_context, mock_user_input_manager):
    # Test that additions on top of deletions and overlapping deletions are handled correctly
    # Additionally test that FileUpdate along with Additions and Deletions works correctly
    file_path = Path("test.py")
    with open(file_path, "w") as f:
        f.write("")
    new_file_path = Path("test2.py")
    change = AbstractChange(
        file_path,
        [
            Deletion(1, 3, 0),
            Deletion(2, 5, 0),
            Addition(4, ["I end up on Line 1"], 0),
            Deletion(6, 9, 0),
            Deletion(7, 8, 0),
            FileUpdate(new_file_path, 0),
        ],
    )
    code_lines = [
        "Line 0",
        # Added here
        "Line 1",  # Deleted
        "Line 2",  # Deleted
        "Line 3",  # Deleted
        "Line 4",  # Deleted
        "Line 5",
        "Line 6",  # Deleted
        "Line 7",  # Deleted
        "Line 8",  # Deleted
        "Line 9",
    ]
    new_code_lines = change.apply(code_lines, mock_context, mock_user_input_manager)
    assert new_code_lines == ["Line 0", "I end up on Line 1", "Line 5", "Line 9"]
    assert change.file_path == new_file_path


def test_create(temp_testbed, mock_context, mock_user_input_manager):
    # Test that creating a file with FileUpdate works
    new_file_path = Path("test.py")
    change = AbstractChange(
        None,
        [FileUpdate(new_file_path, 0), Addition(2, ["Line 2", "Line 3"], 0)],
    )
    code_lines = []
    new_code_lines = change.apply(code_lines, mock_context, mock_user_input_manager)
    assert new_code_lines == [
        "",
        "",
        "Line 2",
        "Line 3",
    ]
    assert new_file_path.exists()


def test_delete(
    temp_testbed, mock_context, mock_user_input_manager, mock_collect_user_input
):
    mock_collect_user_input.side_effect = ["y"]

    # Test that deleting a file with FileUpdate works
    file_path = Path("test.py")
    with open(file_path, "w") as f:
        f.write("")

    change = AbstractChange(
        file_path,
        [
            FileUpdate(None, 0),
        ],
    )
    code_lines = ["Line 0", "Line 1", "Line 2"]
    change.apply(code_lines, mock_context, mock_user_input_manager)
    assert change.file_path is None
    assert not file_path.exists()


def test_rename(temp_testbed, mock_context, mock_user_input_manager):
    # Test that renaming a file with FileUpdate works
    file_path = Path("test.py")
    with open(file_path, "w") as f:
        f.write("")
    new_file_path = Path("test2.py")
    newest_file_path = Path("test3.py")
    change = AbstractChange(
        file_path,
        [FileUpdate(new_file_path, 0), FileUpdate(newest_file_path, 0)],
    )
    code_lines = ["Line 0", "Line 1", "Line 2"]
    new_code_lines = change.apply(code_lines, mock_context, mock_user_input_manager)
    assert new_code_lines == ["Line 0", "Line 1", "Line 2"]
    assert change.file_path == newest_file_path
    assert not file_path.exists()
    assert not new_file_path.exists()
    assert newest_file_path.exists()
