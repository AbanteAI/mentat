from __future__ import annotations

import asyncio
import hashlib
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, List, Literal, Optional, Union

from jinja2 import Environment, PackageLoader, select_autoescape

if TYPE_CHECKING:
    from mentat.transcripts import Transcript


mentat_dir_path = Path.home() / ".mentat"

# package_name should always be "mentat" - but this will work if package name is changed
package_name = __name__.split(".")[0]
resources_path = Path("resources")
conversation_viewer_path = Path("conversation_viewer.html")


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def run_subprocess_async(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_output = stderr.decode("utf-8").strip() if stderr else ""
        raise Exception(f"Subprocess failed with error: {error_output}")

    output = stdout.decode("utf-8").strip() if stdout else ""

    return output


# Useful for using functions designed to work with LLMs on prepared strings
async def convert_string_to_asynciter(
    input_str: str,
    chunk_size: int,
    role: Optional[Literal["system", "user", "assistant", "tool"]] = "assistant",
) -> AsyncIterator[str]:
    for i in range(0, len(input_str), chunk_size):
        yield input_str[i : i + chunk_size]


def fetch_resource(resource_path: Path) -> Traversable:
    resource = resources.files(package_name).joinpath(str(resources_path / resource_path))
    return resource


def create_viewer(transcripts: list[Transcript]) -> Path:
    env = Environment(
        loader=PackageLoader("mentat", "resources/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("conversation_viewer.jinja")
    html = template.render(transcripts=transcripts[:500])

    viewer_path = mentat_dir_path / conversation_viewer_path
    with viewer_path.open("w") as viewer_file:
        viewer_file.write(html)
    return viewer_path


async def add_newline(
    iterator: AsyncIterator[str],
    role: Optional[Literal["system", "user", "assistant", "tool"]] = "assistant",
) -> AsyncIterator[str]:
    """
    The model often doesn't end it's responses in a newline;
    adding a newline makes it significantly easier for us to parse.
    """
    last_chunk = None
    async for chunk in iterator:
        last_chunk = chunk
        yield chunk
    if last_chunk is not None:
        yield "\n"


def get_relative_path(path: Path, target: Path) -> Path:
    """Get the relative path of a file from a given directory.

    This function is a 'backport' of `PurePath.relative_to` from Python 3.12 and later which has directory walk-up
    support. See https://docs.python.org/3.12/library/pathlib.html#pathlib.PurePath.relative_to.

    Args:
        path (Path): The path to get the relative path of. This path must exist on the filesystem.
        target (Path): The target path to base the relative path off of. This path must exist on the filesystem.

    Returns:
        Path: A relative path
    """
    path = path.resolve()
    target = target.resolve()

    if path.is_relative_to(target):
        relative_path = path.relative_to(target)
    else:
        relative_parts: List[Union[str, Path]] = []
        parent = target
        while not path.is_relative_to(parent):
            relative_parts.append("..")
            parent = parent.parent
        relative_parts.append(path.relative_to(parent))
        relative_path = Path(*relative_parts)

    return relative_path


# TODO: replace this with something that doesn't load the file into memory
def is_file_text_encoded(abs_path: Path):
    """Checks if a file is text encoded."""
    try:
        # The ultimate filetype test
        with open(abs_path, "r") as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False
