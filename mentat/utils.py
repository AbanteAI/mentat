import asyncio
import hashlib
from typing import AsyncGenerator


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
