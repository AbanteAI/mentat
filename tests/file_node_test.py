from asyncio import gather
from pathlib import Path

import pytest

from mentat.file_node import Node


def test_node_init(temp_testbed):
    root_path = Path(temp_testbed)
    root = Node(root_path)
    assert root.path == root_path
    assert len(root.children) > 1

    # Initialize and iterate over all children, depth-first, alphabetically
    all_children = list(r.relative_path() for r in root.iter_nodes())
    expected = [
        ".",
        ".gitignore",
        "__init__.py",
        "multifile_calculator",
        "multifile_calculator/__init__.py",
        "multifile_calculator/calculator.py",
        "multifile_calculator/operations.py",
        "scripts",
        "scripts/calculator.py",
        "scripts/echo.py",
        "scripts/graph_class.py",
    ]
    assert all_children == [Path(e) for e in expected]

    # Access children by relative path, absolute path or string
    echo = root["scripts/echo.py"]
    echo2 = root[Path("scripts/echo.py")]
    echo3 = root[Path("scripts/echo.py").absolute()]
    assert echo == echo2 == echo3

    assert echo.root().path.name == root.path.name
    assert echo.relative_path() == Path("scripts/echo.py")


@pytest.mark.asyncio
async def test_node_checksum(temp_testbed):
    root_path = Path(temp_testbed)
    root = Node(root_path)
    echo = root["scripts/echo.py"]
    unaffected = root["multifile_calculator"]

    # Checksums work on files or directories
    initial_checksum = await echo.get_checksum()
    initial_unaffected = await unaffected.get_checksum()
    await echo.write_text("Updated text")
    new_checksum = await echo.get_checksum()
    new_unaffected = await unaffected.get_checksum()
    assert initial_checksum != new_checksum
    assert initial_unaffected == new_unaffected
