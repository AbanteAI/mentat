import subprocess

from mentat.commands import Command, HelpCommand, InvalidCommand


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
