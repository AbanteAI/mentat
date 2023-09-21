#!/usr/bin/env python
# If you think your last mentat run was useful you can turn the transcript into a training example:
# ./scripts/log_to_training_example.py
import argparse
import json
import os
import re

parser = argparse.ArgumentParser(
    description="Turn a log file into an OpenAI conversation."
)
parser.add_argument(
    "--log_file",
    type=str,
    default="~/.mentat/logs/latest.log",
    help="The log file to parse.",
)
args = parser.parse_args()
log_file = os.path.expanduser(args.log_file)


def log_file_to_conversation(filename):
    messages = []

    with open(filename, "r") as f:
        content = f.read()

    pattern = re.compile(
        r"DEBUG - (System|Assistant|User|Code) Message:\n(.*?)\n\d\d\d\d-\d\d-\d\d ",
        re.DOTALL,
    )
    matches = pattern.findall(content)
    added_code_message = False
    for match in matches:
        kind = match[0]
        message = match[1]
        if kind == "Code" and not added_code_message:
            added_code_message = True
            messages.append({"role": "system", "content": message})
        if kind == "System":
            messages.append({"role": "system", "content": message})
        if kind == "Assistant":
            messages.append({"role": "assistant", "content": message})
        if kind == "User":
            messages.append({"role": "assistant", "content": message})

    return json.dumps({"messages": messages})


print(log_file_to_conversation(log_file))
