import json
import platform
import subprocess
from functools import cache
from pathlib import Path

from mentat.errors import MentatError


@cache
def ensure_ctags_installed() -> None:
    try:
        subprocess.run(
            ["ctags", "--help"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return
    except subprocess.CalledProcessError:
        pass

    os_name = platform.system()
    match os_name:
        case "Linux":
            suggested_install_command = "sudo apt install universal-ctags"
        case "Darwin":  # macOS
            suggested_install_command = "brew install universal-ctags"
        case "Windows":
            suggested_install_command = "choco install universal-ctags"
        case _:
            suggested_install_command = None

    error_message = "Missing Dependency: universal-ctags (required for auto-context)"
    if suggested_install_command:
        error_message += f"\nSuggested install method for your OS: `{suggested_install_command}`"
    error_message += "\nSee README.md for full installation details."
    raise MentatError(error_message)


def get_ctag_lines_and_names(path: Path) -> list[tuple[int, str]]:
    ensure_ctags_installed()

    json_tags = (
        subprocess.check_output(
            ["ctags", "--output-format=json", "--fields=+n", str(path)],
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        )
        .strip()
        .splitlines()
    )

    lines_and_names: list[tuple[int, str]] = []
    for json_tag in json_tags:
        tag_dict = json.loads(json_tag)
        name = tag_dict["name"]
        if "scope" in tag_dict:
            name = f"{tag_dict['scope']}.{name}"
        line = tag_dict["line"]
        lines_and_names.append((line, name))

    return lines_and_names
