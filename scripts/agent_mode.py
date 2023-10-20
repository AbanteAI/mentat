import argparse
import asyncio
import os
from pathlib import Path
from textwrap import dedent

import openai
from dotenv import load_dotenv
from termcolor import cprint

from mentat.python_client.client import PythonClient

# Set up the OpenAI API
load_dotenv("~/.mentat/.env")
openai.api_key = os.getenv("OPENAI_API_KEY")


def get_next_input(conversation_messages):
    response = openai.ChatCompletion.create(
        model="gpt-4-0314",
        messages=conversation_messages,
        temperature=0.5,
    )

    return response.choices[0].message.content


last_code_message = None


def add_code_status_message_if_changed(file_path, conversation_messages):
    global last_code_message
    with open(file_path, "r") as f:
        code = f.read()
    new_code_message = f"CODE STATUS\n{code}"
    if new_code_message != last_code_message:
        conversation_messages.append({"role": "system", "content": new_code_message})
        last_code_message = new_code_message


async def run(file_path: str, main_prompt: str):
    initial_system_message = dedent("""\
        // You are a large language model that's part of an automated coding system.
        // You will not write code directly, but instead interact with Mentat, an AI coding assistant.
        // Mentat may not always perform well, part of your job is to overcome its limitations.
        // You will be given a coding task, and then use Mentat to complete it.
        // Mentat will access and modify a single file called script_x.py.
        // Check Mentat's work closely, giving it feedback and asking it to rework the code until it's correct.
        // After this message, every message will be from Mentat itself except for messages that begin with CODE STATUS
        // Messages beginning with CODE STATUS will just show you the current state of the script, so you can check Mentat's work.
        // You will receive a new CODE STATUS message every time the file has been changed.
        // You will also recieve a CODE STATUS message immediately after this message, to show you the initial state of the file.
        // You are in charge, do not ask it what it can do for you.
        // You should act as if you are a human interacting with Mentat, as it's designed to be used by humans.
        // Mentat asks for confirmation before making changes, it'll tell you how to approve changes when it asks (Y/N).
        // DO NOT message that work has been completed, announce your intentions, or ask if there's more I'd like you to do.
        // Once your task has been achieved, use `q` to quit.
        // Your task: """)
    initial_system_message += main_prompt
    conversation_messages = [{"role": "system", "content": initial_system_message}]
    add_code_status_message_if_changed(file_path, conversation_messages)

    client = PythonClient(paths=[Path(file_path)])

    await client.startup()

    quitting = False
    while not quitting:
        input_request_message, mentat_output = await client.wait_for_input_request()

        conversation_messages.append({"role": "system", "content": mentat_output})
        print(mentat_output)
        print(">>>>>>>>>>>>>>>>>>>>>>>>")

        add_code_status_message_if_changed(file_path, conversation_messages)
        next_input = get_next_input(conversation_messages)
        cprint(next_input, "magenta")
        print("<<<<<<<<<<<<<<<<<<<<<<<<")
        if next_input == "q":
            quitting = True
        await client.call_mentat_with_input_request(next_input, input_request_message)

    had_error = not client.started
    await client.stop()

    if had_error:
        print("Had error")

    acc_msg = client._accumulated_message
    print(acc_msg)
    print(">>>>>>>>>>>>>>>>>>>>>>>>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", type=str)
    parser.add_argument("main_prompt", type=str)
    args = parser.parse_args()
    asyncio.run(run(args.file_path, args.main_prompt))
