import subprocess
from pathlib import Path

import pytest

from mentat.code_context import CodeContext
from mentat.commands import (
    Command,
    ExcludeCommand,
    HelpCommand,
    IncludeCommand,
    InvalidCommand,
)


def test_invalid_command():
    assert isinstance(Command.create_command("non-existent"), InvalidCommand)


@pytest.mark.asyncio
async def test_help_command(mock_stream):
    command = Command.create_command("help")
    await command.apply()
    assert isinstance(command, HelpCommand)


@pytest.mark.asyncio
async def test_commit_command(mock_stream, temp_testbed):
    file_name = "test_file.py"
    with open(file_name, "w") as f:
        f.write("# Commit me!")

    command = Command.create_command("commit")
    await command.apply("commit", "test_file committed")
    assert subprocess.check_output(["git", "diff", "--name-only"], text=True) == ""


@pytest.mark.asyncio
async def test_include_command(mock_stream, mock_config):
    code_context = await CodeContext.create(
        config=mock_config,
        paths=[],
        exclude_paths=[],
    )
    command = Command.create_command("include", code_context=code_context)
    assert isinstance(command, IncludeCommand)
    await command.apply("__init__.py")
    assert Path("__init__.py").resolve() in code_context.include_files


@pytest.mark.asyncio
async def test_exclude_command(mock_stream, mock_config):
    code_context = await CodeContext.create(
        config=mock_config,
        paths=[Path("__init__.py")],
        exclude_paths=[],
    )
    command = Command.create_command("exclude", code_context=code_context)
    assert isinstance(command, ExcludeCommand)
    await command.apply("__init__.py")
    assert Path("__init__.py").resolve() not in code_context.include_files
