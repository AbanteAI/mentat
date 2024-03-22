import re
from typing import Optional

import packaging.version
import requests

from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path
from mentat.version import __version__


def get_changelog() -> Optional[str]:
    try:
        response = requests.get("https://raw.githubusercontent.com/AbanteAI/mentat/main/CHANGELOG.rst")
        if response.status_code == 200:
            return response.text
        else:
            return None
    except Exception:
        return None


def get_latest_changelog(full_changelog: Optional[str] = None) -> Optional[str]:
    if full_changelog is None:
        full_changelog = get_changelog()
    if full_changelog is None:
        return None
    try:
        sections = re.split("\n[^\n]+\n-{1,}\n", full_changelog)
        return sections[1].strip()
    except Exception:
        return None


def check_version():
    ctx = SESSION_CONTEXT.get()

    try:
        response = requests.get("https://pypi.org/pypi/mentat/json")
        data = response.json()
        latest_version = data["info"]["version"]

        if packaging.version.parse(__version__) < packaging.version.parse(latest_version):
            ctx.stream.send(
                f"Version v{latest_version} of Mentat is available. If pip was used to"
                " install Mentat, upgrade with:",
                style="warning",
            )
            ctx.stream.send("pip install --upgrade mentat", style="warning")
            changelog = get_latest_changelog()
            if changelog:
                ctx.stream.send("Upgrade for the following features/improvements:", style="warning")
                ctx.stream.send(changelog, style="warning")

        else:
            last_version_check_file = mentat_dir_path / "last_version_check"
            if last_version_check_file.exists():
                with open(last_version_check_file, "r") as f:
                    last_version_check = f.read()
                if packaging.version.parse(last_version_check) < packaging.version.parse(__version__):
                    changelog = get_latest_changelog()
                    if changelog:
                        ctx.stream.send(f"Thanks for upgrading to v{__version__}.", style="info")
                        ctx.stream.send("Changes in this version:", style="info")
                        ctx.stream.send(changelog, style="info")
            with open(last_version_check_file, "w") as f:
                f.write(__version__)
    except Exception as err:
        ctx.stream.send(f"Error checking for most recent version: {err}", style="error")


def check_model():
    ctx = SESSION_CONTEXT.get()
    model = ctx.config.model
    if "gpt-4" not in model and "opus" not in model:
        ctx.stream.send(
            "Warning: The only recommended models are GPT-4 and Claude 3 Opus. "
            "You may experience issues with quality. This model may not be able to "
            "respond in mentat's edit format.",
            style="warning",
        )
        if "gpt-3.5" not in model and "claude-3" not in model:
            ctx.stream.send(
                "Warning: Mentat does not know how to calculate costs or context" " size for this model.",
                style="warning",
            )
