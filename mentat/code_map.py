import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .session_stream import SESSION_STREAM
from .utils import run_subprocess_async


async def get_code_map(
    root: Path, file_path: Path, exclude_signatures: bool = False
) -> list[str]:
    # Create ctags from executable in a subprocess
    ctags_cmd_args = [
        "--extras=-F",
        "--input-encoding=utf-8",
        "--output-format=json",
        "--output-encoding=utf-8",
        # "--fields=+n",
    ]
    if exclude_signatures:
        ctags_cmd_args.append("--fields=-s")
    else:
        ctags_cmd_args.append("--fields=+S")
    ctags_cmd = ["ctags", *ctags_cmd_args, str(Path(root).joinpath(file_path))]

    output = await run_subprocess_async(*ctags_cmd)
    output_lines = output.splitlines()

    # Extract subprocess stdout into python objects
    ctags = set[tuple[Path, ...]]()
    for output_line in output_lines:
        try:
            tag = json.loads(output_line)
        except json.decoder.JSONDecodeError as err:
            await SESSION_STREAM.get().send(
                f"Error parsing ctags output: {err}\n{repr(output_line)}",
                color="yellow",
            )
            continue

        scope = tag.get("scope")
        kind = tag.get("kind")
        name = tag.get("name")
        signature = tag.get("signature")
        # line_number = tag.get("line")  # TODO: Use to split CodeFeatures in CodeContext

        last = name
        if signature:
            last += " " + signature

        res: list[Any] = []
        if scope:
            res.append(scope)
        res += [kind, last]

        ctags.add(tuple(res))

    if len(ctags) == 0:
        return []

    # Build LLM-readable string representation of ctag objects
    sorted_tags = sorted(ctags)
    output = ""
    last = [None] * len(sorted_tags[0])
    tab = "\t"
    for tag in sorted_tags:
        tag = list(tag)

        num_common = 0
        for i in range(len(last) + 1):
            if i == len(last):
                break
            if last[i] != tag[i]:
                num_common = i
                break

        indent = tab * num_common
        rest = tag[num_common:]

        for item in rest:
            output += indent + str(item) + "\n"
            indent += tab
        last = tag
    return output.splitlines()


async def check_ctags_disabled() -> str | None:
    try:
        cmd = ["ctags", "--version"]
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode("utf-8")
        output = output.lower()

        cmd = " ".join(cmd)
        if "universal ctags" not in output:
            return f"{cmd} does not claim to be universal ctags"
        if "+json" not in output:
            return f"{cmd} does not list +json support"

        with tempfile.TemporaryDirectory() as tempdir:
            hello_py = Path(tempdir) / "hello.py"
            with open(hello_py, "w", encoding="utf-8") as f:
                f.write("def hello():\n    print('Hello, world!')\n")
            await get_code_map(Path(tempdir), hello_py)
        return
    except FileNotFoundError:
        return "ctags executable not found"
    except Exception as e:
        return f"error running universal-ctags: {e}"
