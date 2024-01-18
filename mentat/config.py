from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from json import JSONDecodeError
from pathlib import Path

import attr
from attr import converters, validators

from mentat.git_handler import get_git_root_for_path
from mentat.llm_api_handler import known_models
from mentat.parsers.parser import Parser
from mentat.parsers.parser_map import parser_map
from mentat.session_context import SESSION_CONTEXT
from mentat.terminal.themes import themes
from mentat.utils import mentat_dir_path

config_file_name = Path(".mentat_config.json")
user_config_path = mentat_dir_path / config_file_name


def int_or_none(s: str | None) -> int | None:
    if s is not None:
        return int(s)
    return None


bool_autocomplete = ["True", "False"]


@attr.define
class Config:
    _errors: list[str] = attr.field(factory=list)

    # Model specific settings
    model: str = attr.field(
        default="gpt-4-1106-preview",
        metadata={"auto_completions": list(known_models.keys())},
    )
    feature_selection_model: str = attr.field(
        default="gpt-4-1106-preview",
        metadata={"auto_completions": list(known_models.keys())},
    )
    embedding_model: str = attr.field(
        default="text-embedding-ada-002",
        metadata={
            "auto_completions": [
                model.name for model in known_models.values() if model.embedding_model
            ]
        },
    )
    temperature: float = attr.field(
        default=0.2, converter=float, validator=[validators.le(1), validators.ge(0)]
    )

    maximum_context: int | None = attr.field(
        default=None,
        metadata={
            "description": (
                "The maximum number of lines of context to include in the prompt. It is"
                " inferred automatically for openai models but you can still set it to"
                " save costs. If not set for non-openai models, it defaults to 4096."
            ),
        },
        converter=int_or_none,
        validator=validators.optional(validators.ge(0)),
    )
    token_buffer: int = attr.field(
        default=1000,
        metadata={
            "description": (
                "The amount of tokens to always be reserved as a buffer for user and"
                " model messages."
            ),
        },
    )
    parser: Parser = attr.field(  # pyright: ignore
        default="block",
        metadata={
            "description": (
                "The format for the LLM to write code in. You probably don't want to"
                " mess with this setting."
            ),
            "auto_completions": list(parser_map.keys()),
        },
        converter=parser_map.get,  # pyright: ignore
        validator=validators.instance_of(Parser),  # pyright: ignore
    )
    no_parser_prompt: bool = attr.field(
        default=False,
        metadata={
            "description": (
                "Whether to include the parser prompt in the system message. This"
                " should only be set to true for fine tuned models."
            ),
            "auto_completions": bool_autocomplete,
        },
        converter=converters.optional(converters.to_bool),
    )
    revisor: bool = attr.field(
        default=False,
        metadata={
            "description": (
                "Enables or disables a revisor tweaking model edits after they're made."
                " The revisor will use the same model regular edits do."
            ),
            "auto_completions": bool_autocomplete,
        },
        converter=converters.optional(converters.to_bool),
    )
    sampler: bool = attr.field(
        default=False,
        metadata={
            "description": (
                "Automatically saves a git diff snapshot for the sampler on startup."
            ),
            "auto_completions": bool_autocomplete,
        },
        converter=converters.optional(converters.to_bool),
    )

    # Context specific settings
    file_exclude_glob_list: list[str] = attr.field(
        factory=list,
        metadata={"description": "List of glob patterns to exclude from context"},
    )
    auto_context_tokens: int = attr.field(  # pyright: ignore
        default=0,
        metadata={
            "description": (
                "Automatically selects code files for every request to include in"
                " context. Adds this many tokens to context each request."
            ),
            "abbreviation": "a",
            "const": 5000,
        },
        converter=int,
        validator=validators.ge(0),  # pyright: ignore
    )
    llm_feature_filter: int = attr.field(  # pyright: ignore
        default=0,
        metadata={
            "description": (
                "Send this many tokens of auto-context-selected code files to an LLM"
                " along with the user_prompt to post-select only files which are"
                " relevant to the task. Post-files will then be sent to the LLM again"
                " to respond to the user's prompt."
            ),
            "abbreviation": "l",
            "const": 5000,
        },
        converter=int,
        validator=validators.ge(0),  # pyright: ignore
    )

    # Sample specific settings
    sample_repo: str | None = attr.field(
        default=None,
        metadata={
            "description": "A public url for a cloneable git repository to sample from."
        },
    )
    sample_merge_base_target: str | None = attr.field(
        default=None,
        metadata={
            "description": "The branch or commit to use as the merge base for samples."
        },
    )

    theme: str | None = attr.field(  # pyright: ignore
        default="light",
        metadata={
            "description": (
                "Theme for interaction possible choices are light, dark or none."
            )
        },
        validator=validators.in_(themes.keys()),  # pyright: ignore
    )

    # Only settable by config file
    input_style: list[tuple[str, str]] = attr.field(
        factory=lambda: [
            ["", "#9835bd"],
            ["prompt", "#ffffff bold"],
            ["continuation", "#ffffff bold"],
        ],
        metadata={
            "description": "Styling information for the terminal.",
            "no_flag": True,
            "no_midsession_change": True,
        },
    )

    @classmethod
    def get_fields(cls) -> list[str]:
        return [
            field.name for field in attr.fields(cls) if not field.name.startswith("_")
        ]

    @classmethod
    def add_fields_to_argparse(cls, parser: ArgumentParser) -> None:
        for field in attr.fields(cls):
            if "no_flag" in field.metadata:
                continue
            name = [f"--{field.name.replace('_', '-')}"]
            if "abbreviation" in field.metadata:
                name.append(f"-{field.metadata['abbreviation'].replace('_', '-')}")

            arguments = {
                "help": field.metadata.get("description", ""),
            }
            if "const" in field.metadata:
                arguments["nargs"] = "?"
                arguments["const"] = field.metadata["const"]

            if field.type == "bool":
                if arguments.get("default", False):
                    arguments["action"] = "store_false"
                else:
                    arguments["action"] = "store_true"
            elif field.type == "int":
                arguments["type"] = int
            elif field.type == "float":
                arguments["type"] = float
            elif field.type == "list[str]":
                arguments["nargs"] = "*"

            parser.add_argument(*name, **arguments)

    @classmethod
    def create(cls, cwd: Path, args: Namespace | None = None) -> Config:
        config = Config()

        # Each method overwrites the previous so they are in order of precedence
        config.load_file(user_config_path)
        git_root = get_git_root_for_path(cwd, raise_error=False)
        if git_root is not None:
            config.load_file(git_root / config_file_name)
        config.load_file(cwd / config_file_name)

        if args is not None:
            config.load_namespace(args)

        return config

    def load_namespace(self, args: Namespace) -> None:
        for field in attr.fields(Config):
            if field.name in args and field.name != "_errors":
                value = getattr(args, field.name)
                if value is not None and value != field.default:
                    try:
                        setattr(self, field.name, value)
                    except (ValueError, TypeError) as e:
                        self.error(f"Warning: Illegal value for {field}: {e}")

    def load_file(self, path: Path) -> None:
        if path.exists():
            with open(path) as config_file:
                try:
                    config = json.load(config_file)
                except JSONDecodeError:
                    self.error(
                        f"Warning: Config {path} contains invalid json; ignoring user"
                        " configuration file"
                    )
                    return
            for field in config:
                if hasattr(self, field):
                    try:
                        setattr(self, field, config[field])
                    except (ValueError, TypeError) as e:
                        self.error(
                            f"Warning: Config {path} contains invalid value for"
                            f" setting: {field}\n{e}"
                        )
                else:
                    self.error(
                        f"Warning: Config {path} contains unrecognized setting: {field}"
                    )

    def error(self, message: str) -> None:
        self._errors.append(message)
        try:
            self.send_errors_to_stream()
        except LookupError:
            pass

    def send_errors_to_stream(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        for error in self._errors:
            stream.send(error, style="warning")
        self._errors = []
