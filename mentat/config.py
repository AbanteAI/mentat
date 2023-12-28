from __future__ import annotations

import os
from pathlib import Path
import yaml
import shutil
import attr

from mentat import user_session

from mentat.git_handler import get_git_root_for_path
from mentat.parsers.parser_map import parser_map
from mentat.parsers.block_parser import BlockParser
from mentat.utils import mentat_dir_path, dd
from dataclasses import dataclass, field
from dataclasses_json import DataClassJsonMixin
from typing import Union
from typing import Any, Dict, List, Optional

config_file_name = Path(".mentat_config.yaml")
user_config_path = mentat_dir_path / config_file_name

APP_ROOT = Path.cwd()
MENTAT_ROOT = Path(__file__).parent
USER_MENTAT_ROOT = Path.home() / ".mentat"
GIT_ROOT = get_git_root_for_path(APP_ROOT, raise_error=False)

def int_or_none(s: str | None) -> int | None:
    if s is not None:
        return int(s)
    return None


bool_autocomplete = ["True", "False"]


@dataclass()
class RunSettings(DataClassJsonMixin):
    file_exclude_glob_list: List[Path] = field(default_factory=list)
    auto_context: bool = False
    auto_tokens: int = 8000
    #Automatically selects code files for every request to include in context. Adds this many tokens to context each request.
    auto_context_tokens: int = 0

@dataclass()
class AIModelSettings(DataClassJsonMixin):
    model: str = "gpt-4-1106-preview"
    feature_selection_model: str = "gpt-4-1106-preview"
    embedding_model: str = "text-embedding-ada-002"
    prompts: Dict[str, Path] = field(
        default_factory=lambda: {
            "agent_file_selection_prompt": Path("text/agent_file_selection_prompt.txt"),
            "agent_command_selection_prompt": Path("text/agent_command_selection_prompt.txt"),
            "block_parser_prompt": Path("text/block_parser_prompt.txt"),
            "feature_selection_prompt": Path("text/feature_selection_prompt.txt"),
            "replacement_parser_prompt": Path("text/replacement_parser_prompt.txt"),
            "unified_diff_parser_prompt": Path("text/unified_diff_parser_prompt.txt"),
            "json_parser_prompt": Path("text/json_parser_prompt.txt")
        }
    )
    temperature: float = 0.2

    maximum_context: Optional[int] = None
    token_buffer: int = 1000
    no_parser_prompt: bool = False

@dataclass()
class UISettings(DataClassJsonMixin):
    input_style: Dict[str, str] = field(
        default_factory=lambda: {
            "": "#9835bd",
            "prompt": "#ffffff bold",
            "continuation": "#ffffff bold",
        }
    )

@dataclass()
class ParserSettings:
    # The type of parser that should be ued
    parser: Any = BlockParser(),
    parser_type: str = "block"


@dataclass
@attr.s(auto_attribs=True)
class YamlConfig:
    file_exclude_glob_list: List[str] = field(default_factory=lambda:[])
    model: str = "gpt-4-1106-preview"
    temperature: float = 0.2
    prompt_type: str = "text"
    maximum_context: int = 16000
    auto_context_tokens: int = 0
    format: str = "block"
    input_style: Dict[str, str] = field(
        default_factory=lambda: {
            "": "#9835bd",
            "prompt": "#ffffff bold",
            "continuation": "#ffffff bold",
        }
    )

    def __getitem__(self, item: str) -> Any:
        return self.__dict__[item]

    @classmethod
    def get_fields(cls):
        return list(cls.__annotations__.keys())

@dataclass()
class MentatConfig:
    # Directory where the mentat is running
    root: Path = field(default_factory=lambda: APP_ROOT),
    user_config_path: Path = field(default_factory=lambda: user_config_path)

    run: RunSettings = field(default_factory=RunSettings)
    ai: AIModelSettings = field(default_factory=AIModelSettings)
    ui: UISettings = field(default_factory=UISettings)
    parser: ParserSettings = field(default_factory=ParserSettings)

def load_yaml(path: str) -> dict[str, Any | None]:
    """Load the data from the YAML file."""
    with open(path, 'r') as file:
        return yaml.safe_load(file)

def merge_configs(original: dict[str, Optional[Any]], new: dict[str, Optional[Any]]) -> dict[str, Optional[Any]]:
    """Merge two dictionaries, with the second one overwriting the values in the first one."""
    original.update(new)  # Update the original dict with the new one
    return original  # Return the merged dict

def yaml_to_config(yaml_dict: dict[str, Any]) -> dict[str, Any | None]:
    """gets the allowed config settings from a YAML"""

    config = {
        "model": yaml_dict.get("model", "gpt-3"),
        "prompt_type": yaml_dict.get("prompt_type", "text"),
        "maximum_context": yaml_dict.get("maximum_context", 2048),
        "input_style": yaml_dict.get("input_style",
                                     [["", "#000000"],
                                      ["prompt", "#000000 bold"],
                                      ["continuation", "#000000 bold"]]),
        "format": yaml_dict.get('format', 'block'),
        "sampler_repo": yaml_dict.get('sampler', {}).get('repo', None),
        "sampler_merge_base_target": yaml_dict.get('sampler', {}).get('merge_base_target', None)
    }

    if yaml_dict.get("file_exclude_glob_list") is None:
        config["file_exclude_glob_list"] = []
    else:
        config["file_exclude_glob_list"] = yaml_dict["file_exclude_glob_list"]

    return config

def init_config() -> None:
    """Initialize the configuration file if it doesn't exist."""
    git_root = get_git_root_for_path(APP_ROOT, raise_error=False)
    if git_root is not None:
        default_conf_path = os.path.join(MENTAT_ROOT, 'resources', 'conf', '.mentatconf.yaml')
        current_conf_path = os.path.join(git_root, '.mentatconf.yaml')

        if not os.path.exists(current_conf_path):
            shutil.copy(default_conf_path, current_conf_path)


def load_prompts(prompt_type: str):

    if prompt_type == "markdown":
        return {
            "agent_file_selection_prompt" : Path("markdown/agent_file_selection_prompt.md"),
            "agent_command_selection_prompt" : Path("markdown/agent_command_selection_prompt.md"),
            "block_parser_prompt" : Path("markdown/block_parser_prompt.md"),
            "feature_selection_prompt" : Path("markdown/feature_selection_prompt.md"),
            "replacement_parser_prompt" : Path("markdown/replacement_parser_prompt.md"),
            "unified_diff_parser_prompt" : Path("markdown/unified_diff_parser_prompt.md"),
            "json_parser_prompt" : Path("markdown/json_parser_prompt.md"),
        }

    return {
        "agent_file_selection_prompt": Path("text/agent_file_selection_prompt.txt"),
        "agent_command_selection_prompt": Path("text/agent_command_selection_prompt.txt"),
        "block_parser_prompt": Path("text/block_parser_prompt.txt"),
        "feature_selection_prompt": Path("text/feature_selection_prompt.txt"),
        "replacement_parser_prompt": Path("text/replacement_parser_prompt.txt"),
        "unified_diff_parser_prompt": Path("text/unified_diff_parser_prompt.txt"),
        "json_parser_prompt": Path("text/json_parser_prompt.txt"),
    }

def load_settings(config_session_dict: Optional[dict[str, Any | None]] = None):
    """Load the configuration from the `.mentatconf.yaml` file."""

    user_conf_path = USER_MENTAT_ROOT / '.mentatconf.yaml'
    git_root = get_git_root_for_path(APP_ROOT, raise_error=False)

    yaml_config = YamlConfig()

    if user_conf_path.exists():
        yaml_dict = load_yaml(str(user_conf_path))
        user_config = yaml_to_config(yaml_dict)
        yaml_config.__dict__.update(user_config)

    if git_root is not None:
        git_conf_path = Path(git_root) / '.mentatconf.yaml'
        if git_conf_path.exists():
            yaml_dict = load_yaml(str(git_conf_path))
            git_config = yaml_to_config(yaml_dict)
            yaml_config.__dict__.update(git_config)



    if config_session_dict is not None:
        if 'file_exclude_glob_list' in config_session_dict and config_session_dict['file_exclude_glob_list'] is not None:
            yaml_config.file_exclude_glob_list.extend(config_session_dict['file_exclude_glob_list'])

        if 'model' in config_session_dict and config_session_dict['model'] is not None:
            yaml_config.model = str(config_session_dict['model'])

        if 'temperature' in config_session_dict and config_session_dict['temperature'] is not None:
            yaml_config.temperature = str(config_session_dict['temperature'])

        if 'maximum_context' in config_session_dict and config_session_dict['maximum_context'] is not None:
            yaml_config.maximum_context = str(config_session_dict['maximum_context'])

    file_exclude_glob_list: List[str] = yaml_config['file_exclude_glob_list']

    #always ignore .mentatconf
    file_exclude_glob_list.append(".mentatconf.yaml")

    run_settings = RunSettings(
        file_exclude_glob_list=[Path(p) for p in file_exclude_glob_list], # pyright: ignore[reportUnknownVariableType]
        auto_context_tokens=yaml_config.auto_context_tokens
    )

    ui_settings = UISettings(
        input_style=yaml_config.input_style or [] # pyright: ignore[reportGeneralTypeIssues]
    )

    ai_model_settings = AIModelSettings(
        model=yaml_config.model,
        temperature=yaml_config.temperature,
        prompts=load_prompts(yaml_config.prompt_type),
        feature_selection_model=yaml_config.model,
        maximum_context=yaml_config.maximum_context
    )

    parser_type = yaml_config.format
    parser_settings = ParserSettings(
        parser_type=parser_type,
        parser=parser_map[parser_type]
    )

    user_session.set("config", MentatConfig(
        run=run_settings,
        ai=ai_model_settings,
        ui=ui_settings,
        parser=parser_settings
    ))


def update_config(session_config: Dict[str, Union[List[str], None, str, int, float]]) -> None:
    """Reload the configuration using the provided keyword arguments."""
    load_settings(session_config)


def load_config() -> None:
    init_config()
    load_settings()
