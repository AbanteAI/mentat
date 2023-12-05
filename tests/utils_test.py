from pathlib import Path

from mentat.utils import get_relative_path


def test_get_relative_path(temp_testbed: Path):
    # Test path in same directory
    path = Path("__init__.py")
    target = temp_testbed
    assert get_relative_path(path, target) == Path("__init__.py")

    # Test path in parent directory
    path = Path("__init__.py")
    target = temp_testbed / "scripts"
    assert get_relative_path(path, target) == Path("../__init__.py")

    # Test path in child directory
    path = Path("multifile_calculator/__init__.py")
    target = temp_testbed
    assert get_relative_path(path, target) == Path("multifile_calculator/__init__.py")
