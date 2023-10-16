from pathlib import Path

from mentat.utils import fetch_resource

prompts_path = "prompts"


def read_prompt(file_name: Path) -> str:
    prompt_resource = fetch_resource(prompts_path / file_name)
    with prompt_resource.open("r") as prompt_file:
        prompt = prompt_file.read()
    return prompt
