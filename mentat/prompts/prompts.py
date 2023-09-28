from importlib import resources
from pathlib import Path

from mentat.config_manager import package_name

prompts_path = "prompts"


def read_prompt(file_name: Path) -> str:
    prompt_resource = resources.files(package_name).joinpath(
        str(prompts_path / file_name)
    )
    with prompt_resource.open("r") as prompt_file:
        prompt = prompt_file.read()
    return prompt
