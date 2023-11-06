import asyncio
import hashlib
import json
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path
from typing import AsyncGenerator

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
async def convert_string_to_asyncgen(
    input_str: str, chunk_size: int
) -> AsyncGenerator[dict[str, list[dict[str, dict[str, str]]]], None]:
    for i in range(0, len(input_str), chunk_size):
        yield {"choices": [{"delta": {"content": input_str[i : i + chunk_size]}}]}
    return


def fetch_resource(resource_path: Path) -> Traversable:
    resource = resources.files(package_name).joinpath(
        str(resources_path / resource_path)
    )
    return resource


# TODO: Should we use a templating library (like jinja?) for this?
def create_viewer(
    literal_messages: list[tuple[str, list[tuple[str, list[dict[str, str]] | None]]]]
) -> Path:
    messages_json = json.dumps(literal_messages)
    viewer_resource = fetch_resource(conversation_viewer_path)
    with viewer_resource.open("r") as viewer_file:
        html = viewer_file.read()
    html = html.replace("{{ messages }}", messages_json)

    viewer_path = mentat_dir_path / conversation_viewer_path
    with viewer_path.open("w") as viewer_file:
        viewer_file.write(html)
    return viewer_path
