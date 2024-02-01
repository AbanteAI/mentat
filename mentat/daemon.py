import ast
import re
from pathlib import Path
from textwrap import dedent
from typing import List, Optional, Tuple

import openai
from watchfiles import Change, watch

openai_client = openai.Client()


def get_mentat_comment(filename: Path) -> Optional[Tuple[int, str]]:
    with open(filename, "r") as file:
        for line_number, line in enumerate(file, 1):
            if line.startswith("# @mentat"):
                comment_text = line.split("@mentat", 1)[1].strip()
                return line_number, comment_text
    return None


prompt = """
    You are an expert coding assistant. 

    You will be given a code file and a coding task to complete. Your response will be inserted into 
    the code file. Your response must be valid python code and must adhere strictly to the required 
    format. Put all of your response that's valid python code between '@@start' and '@@end' lines.
    Do not include any examples or instructions in your response. Do not re-write the entire file, 
    just answer the coding task.

    Example Request:

    Code File:
    ```
    def add_numbers(a, b):
        return a + b


    def multiply_numbers(a, b):
        return a * b


    def subtract_numbers(a, b):
        return a - b
    ```

    Code Task: create a new function that divides 2 numbers together.


    Example Response:
    
    @@start
    def divide_numbers(a, b):
        return a / b
    @@end
"""


def generate_code_lines(*, code_file: Path, code_task: str) -> List[str]:
    user_prompt = f"""
        Code File:
        ```
        {code_file.read_text()} 
        ```

        Code Task: {code_task}
    """
    user_prompt = dedent(user_prompt).strip()

    # Call openai
    chat = openai_client.chat.completions.create(
        messages=[
            {"role": "system", "content": dedent(prompt.strip())},
            {"role": "user", "content": user_prompt},
        ],
        model="gpt-4-0125-preview",
    )
    result = chat.choices[0].message.content
    if result is None:
        return []

    # Verify code is valid python (else re-run?)
    pattern = r"@@start(.*?)@@end"
    matches = re.findall(pattern, result, re.DOTALL)
    if len(matches) == 0:
        return []

    match = matches[0]
    try:
        # Parse the code to verify its validity
        ast.parse(match)
    except SyntaxError:
        return []

    return match.splitlines()


def modify_file_lines(*, path: Path, user_prompt: str, code_lines: List[str]):
    with open(path, "r") as file:
        file_lines = file.readlines()

    # Find the line number the user_prompt is on
    line_number = None
    for _line_number, line in enumerate(file_lines, 1):
        if line.strip() == f"# @mentat {user_prompt}":
            line_number = _line_number
    if line_number is None:
        print("Could not find the line number for the user prompt")
        return

    # Modify the comment
    file_lines.pop(line_number - 1)
    file_lines.insert(line_number - 1, f"# [completed] @mentat {user_prompt}\n")

    # Insert the code snippet into the file
    code_line_number = line_number
    for code_line in code_lines:
        if code_line == "":
            continue
        file_lines.insert(code_line_number, f"{code_line}\n")
        code_line_number += 1

    with open(path, "w") as file:
        file.writelines(file_lines)


def process_file_change(path: Path):
    # Get @mentat comment
    comment = get_mentat_comment(path)
    if comment is None:
        return
    comment_line, comment_text = comment
    print(f"{path}:{comment_line} >> {comment_text}")

    # Call openai
    print("Calling openai...")
    code_lines = generate_code_lines(code_file=path, code_task=comment_text)
    if len(code_lines) == 0:
        print("No code snippets generated")
        return
    else:
        print("Code snippets generated:", "\n".join(code_lines))

    # Modify the file
    print("Modifying file...")
    modify_file_lines(path=path, user_prompt=comment_text, code_lines=code_lines)
    print("Done!")


def main(path: Path = Path.cwd()):
    print(f"Watching {path}")
    for changes in watch(path, force_polling=True):
        for change_type, _change_path in changes:
            change_path = Path(_change_path)
            if change_path.is_file() is False:
                continue
            if change_type == Change.modified:
                process_file_change(change_path)
