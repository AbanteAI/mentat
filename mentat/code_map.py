import json
import subprocess
import tempfile
from pathlib import Path

from termcolor import cprint

from mentat.errors import UserError


def get_code_map(root: Path, file_path: Path, exclude_signatures: bool = False) -> str:
    # Create ctags from executable in a subprocess
    ctags_cmd_args = [
        "--extras=-F",
        "--input-encoding=utf-8",
        "--output-format=json",
        "--output-encoding=utf-8",
    ]
    if exclude_signatures:
        ctags_cmd_args.append("--fields=-s")
    else:
        ctags_cmd_args.append("--fields=+S")
    ctags_cmd = ["ctags", *ctags_cmd_args, str(Path(root).joinpath(file_path))]
    output = subprocess.check_output(ctags_cmd, stderr=subprocess.PIPE, text=True)
    output_lines = output.splitlines()

    # Extract subprocess stdout into python objects
    ctags = set[tuple[Path, ...]]()
    for output_line in output_lines:
        try:
            tag = json.loads(output_line)
        except json.decoder.JSONDecodeError as err:
            cprint(f"Error parsing ctags output: {err}", color="yellow")
            cprint(f"{repr(output_line)}\n", color="yellow")
            continue

        scope = tag.get("scope")
        kind = tag.get("kind")
        name = tag.get("name")
        signature = tag.get("signature")

        last = name
        if signature:
            last += " " + signature

        res = [file_path]
        if scope:
            res.append(scope)
        res += [kind, last]

        ctags.add(tuple(res))

    if len(ctags) == 0:
        return f"{file_path}\n"

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

    return output


def check_ctags_executable():
    try:
        cmd = ["ctags", "--version"]
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode("utf-8")
        output = output.lower()

        cmd = " ".join(cmd)
        if "universal ctags" not in output:
            raise UserError(f"{cmd} does not claim to be universal ctags")
        if "+json" not in output:
            raise UserError(f"{cmd} does not list +json support")

        with tempfile.TemporaryDirectory() as tempdir:
            hello_py = Path(tempdir) / "hello.py"
            with open(hello_py, "w", encoding="utf-8") as f:
                f.write("def hello():\n    print('Hello, world!')\n")
            get_code_map(Path(tempdir), hello_py)
    except FileNotFoundError:
        raise UserError("ctags executable not found")
    except Exception as e:
        raise UserError(f"error running universal-ctags: {e}")

    return True
