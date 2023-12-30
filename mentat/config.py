from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dataclasses_json import DataClassJsonMixin

import mentat
from mentat import user_session
from mentat.git_handler import get_git_root_for_path
from mentat.llm_api_handler import known_models
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.parsers.unified_diff_parser import UnifiedDiffParser
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path

config_file_name = Path(".mentat_config.yaml")
user_config_path = mentat_dir_path / config_file_name

APP_ROOT = Path.cwd()
MENTAT_ROOT = Path(__file__).parent
USER_MENTAT_ROOT = Path.home() / ".mentat"
GIT_ROOT = get_git_root_for_path(APP_ROOT, raise_error=False)

bool_autocomplete = ["True", "False"]


@dataclass
class RunSettings(DataClassJsonMixin):
    file_exclude_glob_list: List[Path] = field(default_factory=list)
    auto_context: bool = False
    auto_tokens: int = 8000
    auto_context_tokens: int = 0
    active_plugins: List[str] = field(default_factory=list)

    def __init__(
        self,
        file_exclude_glob_list: Optional[List[Path]] = None,
        active_plugins: Optional[List[str]] = None,
        auto_context: Optional[bool] = None,
        auto_tokens: Optional[int] = None,
        auto_context_tokens: Optional[int] = None,
    ) -> None:
        if file_exclude_glob_list is not None:
            self.file_exclude_glob_list = file_exclude_glob_list
        if active_plugins is not None:
            self.active_plugins = active_plugins
        if auto_context is not None:
            self.auto_context = auto_context
        if auto_tokens is not None:
            self.auto_tokens = auto_tokens
        if auto_context_tokens is not None:
            self.auto_context_tokens = auto_context_tokens


@dataclass
class AIModelSettings(DataClassJsonMixin):
    model: str
    feature_selection_model: str
    embedding_model: str
    prompts: Dict[str, Path]
    temperature: float
    maximum_context: Optional[int]
    token_buffer: int
    no_parser_prompt: bool

    def __init__(
        self,
        model: Optional[str] = "gpt-4-1106-preview",
        feature_selection_model: Optional[str] = "gpt-4-1106-preview",
        embedding_model: Optional[str] = "text-embedding-ada-002",
        prompts: Optional[str] = "text",
        temperature: Optional[float] = 0.2,
        maximum_context: Optional[int] = None,
        token_buffer: Optional[int] = 1000,
        no_parser_prompt: Optional[bool] = False,
    ):
        if model is not None:
            self.load_model(model)
        if feature_selection_model is not None:
            self.feature_selection_model = feature_selection_model
        if embedding_model is not None:
            self.embedding_model = embedding_model
        if prompts is not None:
            self.load_prompts(prompts)
        if temperature is not None:
            self.temperature = temperature
        if maximum_context is not None:
            self.maximum_context = maximum_context
        if token_buffer is not None:
            self.token_buffer = token_buffer
        if no_parser_prompt is not None:
            self.no_parser_prompt = no_parser_prompt

    def load_model(self, model: str) -> None:
        self.model = model
        known_model = known_models.get(model)
        if known_model is not None:
            if hasattr(known_model, "context_size"):
                self.maximum_context = int(known_model.context_size)

    def load_prompts(self, prompt_type: str) -> None:
        prompts_type = {
            "markdown": {
                "agent_file_selection_prompt": Path(
                    "markdown/agent_file_selection_prompt.md"
                ),
                "agent_command_selection_prompt": Path(
                    "markdown/agent_command_selection_prompt.md"
                ),
                "block_parser_prompt": Path("markdown/block_parser_prompt.md"),
                "feature_selection_prompt": Path(
                    "markdown/feature_selection_prompt.md"
                ),
                "replacement_parser_prompt": Path(
                    "markdown/replacement_parser_prompt.md"
                ),
                "unified_diff_parser_prompt": Path(
                    "markdown/unified_diff_parser_prompt.md"
                ),
                "json_parser_prompt": Path("markdown/json_parser_prompt.md"),
            },
            "text": {
                "agent_file_selection_prompt": Path(
                    "text/agent_file_selection_prompt.txt"
                ),
                "agent_command_selection_prompt": Path(
                    "text/agent_command_selection_prompt.txt"
                ),
                "block_parser_prompt": Path("text/block_parser_prompt.txt"),
                "feature_selection_prompt": Path("text/feature_selection_prompt.txt"),
                "replacement_parser_prompt": Path("text/replacement_parser_prompt.txt"),
                "unified_diff_parser_prompt": Path(
                    "text/unified_diff_parser_prompt.txt"
                ),
                "json_parser_prompt": Path("text/json_parser_prompt.txt"),
            },
        }

        self.prompts = prompts_type.get(prompt_type, {})


@dataclass
class UISettings(DataClassJsonMixin):
    input_style: Dict[str, str] = field(
        default_factory=lambda: {
            "": "#9835bd",
            "prompt": "#ffffff bold",
            "continuation": "#ffffff bold",
        }
    )

    def __init__(self, input_style: Optional[Dict[str, str]] = None) -> None:
        if input_style is not None:
            self.input_style = input_style


@dataclass
class ParserSettings(DataClassJsonMixin):
    parser: Any = BlockParser()
    parser_type: str = "block"

    def __init__(self, parser_type: Optional[str] = "block"):
        if parser_type is not None:
            self.load_parser(parser_type)
        else:
            self.load_parser("block")

    def load_parser(self, parser_type: str) -> None:
        parsers = {
            "block": BlockParser,
            "replacement": ReplacementParser,
            "unified-diff": UnifiedDiffParser,
        }

        if parser := parsers.get(parser_type):
            self.parser_type = parser_type
            self.parser = parser()
        else:
            self.parser_type = "block"
            self.parser = parsers["block"]()


@dataclass
class RunningSessionConfig(DataClassJsonMixin):
    model: Optional[str] = "gpt-4-1106-preview"
    temperature: Optional[float] = 0.2
    prompt_type: Optional[str] = "text"
    file_exclude_glob_list: Optional[List[str]] = field(
        default_factory=list
    )  # Use default factory for list
    format: Optional[str] = "block"
    input_style: Optional[Dict[str, str]] = field(
        default_factory=lambda: {  # Use default factory for dict
            "": "#9835bd",
            "prompt": "#ffffff bold",
            "continuation": "#ffffff bold",
        }
    )
    maximum_context: Optional[int] = None
    auto_context_tokens: Optional[int] = 0
    active_plugins: Optional[List[str]] = None

    @classmethod
    def get_fields(cls) -> List[str]:
        return [f.name for f in fields(cls)]


@dataclass
class MentatConfig:
    # Directory where the mentat is running
    root: Path = (
        field(default_factory=lambda: APP_ROOT),
    )  # pyright: ignore[reportGeneralTypeIssues]
    user_config_path: Path = field(default_factory=lambda: user_config_path)

    run: RunSettings = field(default_factory=RunSettings)
    ai: AIModelSettings = field(default_factory=AIModelSettings)
    ui: UISettings = field(default_factory=UISettings)
    parser: ParserSettings = field(default_factory=ParserSettings)


def load_yaml(path: str) -> dict[str, Any | None]:
    """Load the data from the YAML file."""
    with open(path, "r") as file:
        return yaml.safe_load(file)


def init_config() -> None:
    """Initialize the configuration file if it doesn't exist."""
    git_root = get_git_root_for_path(APP_ROOT, raise_error=False)
    if git_root is not None:
        default_conf_path = os.path.join(
            MENTAT_ROOT, "resources", "conf", ".mentatconf.yaml"
        )
        current_conf_path = os.path.join(git_root, ".mentatconf.yaml")

        if not os.path.exists(current_conf_path):
            shutil.copy(default_conf_path, current_conf_path)


def load_settings(config_session: Optional[RunningSessionConfig] = None):
    """Load the configuration from the `.mentatconf.yaml` file."""

    user_conf_path = USER_MENTAT_ROOT / ".mentatconf.yaml"
    git_root = get_git_root_for_path(APP_ROOT, raise_error=False)

    yaml_config = RunningSessionConfig()

    if user_conf_path.exists():
        data = load_yaml(str(user_conf_path))
        # fmt: off
        yaml_config = yaml_config.from_dict(  # pyright: ignore[reportUnknownMemberType]
            kvs=data, infer_missing=True
        )
        # fmt: on

    if git_root is not None:
        git_conf_path = Path(git_root) / ".mentatconf.yaml"
        if git_conf_path.exists():
            data = load_yaml(str(git_conf_path))
            # fmt: off
            yaml_config = yaml_config.from_dict(  # pyright: ignore[reportUnknownMemberType]
                kvs=data, infer_missing=True
            )
            # fmt: on

    # safety checks for missing values
    if yaml_config.file_exclude_glob_list is None:
        yaml_config.file_exclude_glob_list = []

    if yaml_config.active_plugins is None:
        yaml_config.active_plugins = []

    if yaml_config.temperature is None:
        yaml_config.temperature = 0.2

    if config_session is not None:
        if config_session.file_exclude_glob_list is not None:
            yaml_config.file_exclude_glob_list.extend(
                config_session.file_exclude_glob_list
            )

        if config_session.model is not None:
            yaml_config.model = str(config_session.model)

        if config_session.temperature is not None:
            yaml_config.temperature = float(config_session.temperature)

        if config_session.maximum_context is not None:
            yaml_config.maximum_context = int(config_session.maximum_context)

    file_exclude_glob_list: List[str] = yaml_config.file_exclude_glob_list or []

    # always ignore .mentatconf
    file_exclude_glob_list.append(".mentatconf.yaml")

    run_settings = RunSettings(
        file_exclude_glob_list=[
            Path(p) for p in file_exclude_glob_list
        ],  # pyright: ignore[reportUnknownVariableType]
        active_plugins=yaml_config.active_plugins,
        auto_context_tokens=yaml_config.auto_context_tokens,
    )

    ui_settings = UISettings(
        input_style=yaml_config.input_style  # pyright: ignore[reportGeneralTypeIssues]
    )

    ai_model_settings = AIModelSettings(
        model=yaml_config.model,
        temperature=yaml_config.temperature,
        feature_selection_model=yaml_config.model,
        maximum_context=yaml_config.maximum_context,
    )

    parser_type = yaml_config.format
    parser_settings = ParserSettings(parser_type=parser_type)

    user_session.set(
        "config",
        MentatConfig(
            run=run_settings,
            ai=ai_model_settings,
            ui=ui_settings,
            parser=parser_settings,
        ),
    )


mid_session_config = [
    "model",
    "temperature",
    "format",
    "maximum_context",
    "auto_context_tokens",
]


def update_config(setting: str, value: str | float | int) -> None:
    """Reload the configuration using the provided keyword arguments."""
    config = mentat.user_session.get("config")
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    try:
        if setting == "model":
            config.ai.load_model(value)
        elif setting == "temperature":
            config.ai.temperature = float(value)
        elif setting == "format":
            config.parser.load_parser(value)
        elif setting == "maximum_context":
            config.ai.maximum_context = int(value)
        elif setting == "auto_context_tokens":
            config.run.auto_context_tokens = value

        stream.send(f"{setting} set to {value}", color="green")
    except (TypeError, ValueError) as e:
        stream.send(
            f"Illegal value for {setting}: {value}.  Error: {str(e)}", color="red"
        )


def get_config(setting: str) -> None:
    """Reload the configuration using the provided keyword arguments."""
    config = mentat.user_session.get("config")
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream

    if setting == "model":
        stream.send(f"{setting}: {config.ai.model}", color="green")
    elif setting == "temperature":
        stream.send(f"{setting}: {config.ai.temperature}", color="green")
    elif setting == "format":
        stream.send(f"{setting}:{config.parser.parser_type}", color="green")
    elif setting == "maximum_context":
        stream.send(f"{setting}: {config.ai.maximum_context}", color="green")
    elif setting == "auto_context_tokens":
        stream.send(f"{setting}: {config.run.auto_context_tokens}", color="green")


def load_config() -> None:
    init_config()
    load_settings()


def is_active_plugin(plugin: str | None = None) -> bool:
    config = mentat.user_session.get("config")
    if (
        plugin is not None
        and config is not None
        and config.run is not None
        and config.run.active_plugins is not None
        and plugin in config.run.active_plugins
    ):
        return True

    return False
