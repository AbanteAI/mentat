from pathlib import Path

import pytest

from mentat.errors import PathValidationError
from mentat.include_files import (
    is_interval_path,
    validate_and_format_path,
    validate_file_interval_path,
    validate_file_path,
    validate_glob_path,
)


def test_is_interval_path():
    assert not is_interval_path(Path("file.py"))
    assert not is_interval_path(Path("file.py:"))
    assert is_interval_path("file.py:0-1")


def test_validate_file_path():
    # raise on non-absolute file path
    with pytest.raises(PathValidationError):
        validate_file_path(Path("file.py"))

    # raise on non-existent file path
    with pytest.raises(PathValidationError):
        validate_file_path(Path("file.py").resolve())


def test_validate_file_interval_path():
    # raise on non-absolute file interval path
    with pytest.raises(PathValidationError):
        validate_file_interval_path(Path("file.py:0-1"))

    # raise on non-existent file interval path
    with pytest.raises(PathValidationError):
        validate_file_interval_path(Path("file.py:0-1").resolve())

    # raise on no intervals
    file_path = Path("file2.txt").resolve()
    with open(file_path, "w") as file:
        file.write("hello world\nhi hi hi")
    with pytest.raises(PathValidationError):
        validate_file_interval_path(Path(f"{file_path}:"))

    # raise on invalid interval
    with pytest.raises(PathValidationError):
        validate_file_interval_path(Path(f"{file_path}:0-1,10-11"))


def test_validate_glob_path():
    # raise on non-absolute glob path
    with pytest.raises(PathValidationError):
        validate_glob_path(Path("*.py"))

    # raise on no files matching glob
    with pytest.raises(PathValidationError):
        validate_glob_path(Path("*.txt").resolve())


def test_validate_and_format_tilde_home_directory():
    with pytest.raises(PathValidationError) as e_info:
        validate_and_format_path("~/non_existing_file.py", "/fake/cwd")
    assert str(Path.home() / "non_existing_file.py") in str(e_info.value)
