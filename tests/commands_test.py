import subprocess
from pathlib import Path

from mentat.code_context import CodeContext
from mentat.commands import (
    AddCommand,
    Command,
    HelpCommand,
    InvalidCommand,
    RemoveCommand,
)


def test_invalid_command():
    assert isinstance(Command.create_command("non-existent"), InvalidCommand)


def test_help_command():
    command = Command.create_command("help")
    command.apply()
    assert isinstance(command, HelpCommand)


def test_commit_command(temp_testbed):
    file_name = "test_file.py"
    with open(file_name, "w") as f:
        f.write("# Commit me!")

    command = Command.create_command("commit")
    command.apply("commit", "test_file committed")
    assert subprocess.check_output(["git", "diff", "--name-only"], text=True) == ""


def test_add_command(mock_config):
    code_context = CodeContext(
        config=mock_config,
        paths=[],
        exclude_paths=[],
    )
    command = Command.create_command("add")
    assert isinstance(command, AddCommand)
    command.apply("__init__.py", code_context=code_context)
    assert Path("__init__.py") in code_context.files


def test_remove_command(mock_config):
    code_context = CodeContext(
        config=mock_config,
        paths=["__init__.py"],
        exclude_paths=[],
    )
    command = Command.create_command("remove")
    assert isinstance(command, RemoveCommand)
    command.apply("__init__.py", code_context=code_context)
    assert Path("__init__.py") not in code_context.files
