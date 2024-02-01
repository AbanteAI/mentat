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

    You will be given a coding task to complete, where your response will be inserted into an 
    existing file. Your response must be valid python code and must adhere strictly to the required 
    format. Put all of your response that's valid python code between '@@start' and '@@end' lines.
    Do not include any examples or instructions in your response.

    Example 1:

    Example 1 Task: create a new function that multiplies 2 numbers together.

    Example 1 Response:
    
    @@start
    def multiply(a, b):
        return a * b
    @@end


    Example 2:

    Example 2 Task: create a random number generator that returns a number between 1 and 10.

    Example 2 Response:
    
    @@start
    import random

    def random_number():
        return random.randint(1, 10)
    @@end
"""


def generate_code_lines(user_prompt: str) -> List[str]:
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
    code_lines = generate_code_lines(comment_text)
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
