from __future__ import annotations

import os
from pathlib import Path
import yaml
import shutil

from dataclasses import asdict

from mentat.git_handler import get_git_root_for_path
from mentat.parsers.parser_map import parser_map
from mentat.parsers.block_parser import BlockParser
from mentat.utils import mentat_dir_path, dd
from dataclasses import dataclass, field
from dataclasses_json import DataClassJsonMixin
from typing import Optional, List, Tuple
from mentat.parsers.parser import Parser
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional


config_file_name = Path(".mentat_config.yaml")
user_config_path = mentat_dir_path / config_file_name

APP_ROOT = Path.cwd()
MENTAT_ROOT = Path(__file__).parent
USER_MENTAT_ROOT = Path.home() / ".mentat"

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

@dataclass()
class AIModelSettings(DataClassJsonMixin):
    model: str = "gpt-4-1106-preview"
    feature_selection_model: str = "gpt-4-1106-preview"
    embedding_model: str = "text-embedding-ada-002"
    temperature: float = 0.2

    maximum_context: Optional[int] = None
    token_buffer: int = 1000
    no_parser_prompt: bool = False

@dataclass()
class UISettings(DataClassJsonMixin):
    input_style: List[Tuple[str, str]] = field(
        default_factory=lambda: [
            ["", "#9835bd"],
            ["prompt", "#ffffff bold"],
            ["continuation", "#ffffff bold"],
        ]
    )

@dataclass()
class ParserSettings:
    # The type of parser that should be ued
    parser: Parser = BlockParser(),
    parser_type: str = "block"


@dataclass()
class MentatConfig:
    # Directory where the mentat is running
    root = APP_ROOT

    run: RunSettings
    ai: AIModelSettings
    ui: UISettings
    parser: ParserSettings

def load_yaml(path: str) -> dict:
    """Load the data from the YAML file."""
    with open(path, 'r') as file:
        return yaml.safe_load(file)

def merge_configs(original: dict[str, Any | None], new: dict[str, Any | None]) -> dict[str, Any | None]:
    """Merge two dictionaries, with the second one overwriting the values in the first one."""
    original.update(new)  # Update the original dict with the new one
    return original  # Return the merged dict

def yaml_to_config(yaml_dict: dict):
    """gets the allowed config settings from a YAML"""

    return {
        "model": yaml_dict.get("model"),
        "maximum_context": yaml_dict.get("maximum_context"),
        "file_exclude_glob_list": yaml_dict.get("file_exclude_glob_list", []),
        "input_style": yaml_dict.get("input_style"),
        "format": yaml_dict.get("format")
    }

def init_config():
    """Initialize the configuration file if it doesn't exist."""
    default_conf_path = os.path.join(MENTAT_ROOT, 'resources', 'conf', '.mentatconf.yaml')
    current_conf_path = os.path.join(APP_ROOT, '.mentatconf.yaml')

    if not os.path.exists(current_conf_path):
        shutil.copy(default_conf_path, current_conf_path)


def load_settings():
    """Load the configuration from the `.mentatconf.yaml` file."""

    current_conf_path = APP_ROOT / '.mentatconf.yaml'
    user_conf_path = USER_MENTAT_ROOT / '.mentatconf.yaml'
    git_root = get_git_root_for_path(APP_ROOT, raise_error=False)

    yaml_config = {}

    if user_conf_path.exists():
        yaml_dict = load_yaml(str(user_conf_path))
        user_config = yaml_to_config(yaml_dict)
        yaml_config = merge_configs(yaml_config, user_config)

    if git_root is not None:
        git_conf_path = Path(git_root) / '.mentatconf.yaml'
        if git_conf_path.exists():
            yaml_dict = load_yaml(str(git_conf_path))
            git_config = yaml_to_config(yaml_dict)
            yaml_config = merge_configs(yaml_config, git_config)

    if current_conf_path.exists():
        yaml_dict = load_yaml(str(current_conf_path))
        current_path_config = yaml_to_config(yaml_dict)
        yaml_config = merge_configs(yaml_config, current_path_config)

    run_settings = RunSettings(
        file_exclude_glob_list=[Path(p) for p in yaml_config.get("file_exclude_glob_list", [])]
    )

    ui_settings = UISettings(
        input_style=yaml_config.get("input_style", [])
    )

    ai_model_settings = AIModelSettings(
        model=yaml_config.get("model", "gpt-4-1106-preview"),
        feature_selection_model=yaml_config.get("model", "gpt-4-1106-preview"),
        maximum_context=yaml_config.get("maximum_context", 16000)
    )

    parser_type = yaml_config.get("format", "block")
    parser_settings = ParserSettings(
        parser_type=parser_type,
        parser=parser_map[parser_type]
    )

    return {
            "run": run_settings,
            "ai": ai_model_settings,
            "ui": ui_settings,
            "parser": parser_settings,
        }


def update_config(**kwargs):
    """Reload the configuration using the provided keyword arguments."""
    global config
    if config is None:
        return

    # setting the values from kwargs to the global config
    for key, value in kwargs.items():
        setattr(config, key, value)

def load_config() -> MentatConfig:
    init_config()
    settings = load_settings()
    config = MentatConfig(**settings)

    return config


config = load_config()