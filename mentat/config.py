from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from json import JSONDecodeError
from pathlib import Path

import attr
from attr import converters, validators

from mentat.git_handler import get_shared_git_root_for_paths
from mentat.parsers.parser import Parser
from mentat.parsers.parser_map import parser_map
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path

config_file_name = Path(".mentat_config.json")
user_config_path = mentat_dir_path / config_file_name


def int_or_none(s: str | None) -> int | None:
    if s is not None:
        return int(s)
    return None


@attr.define
class Config:
    _errors: list[str] = attr.field(factory=list)

    # Model specific settings
    model: str = attr.field(default="gpt-4-1106-preview")
    feature_selection_model: str = attr.field(default="gpt-4-1106-preview")
    embedding_model: str = attr.field(default="text-embedding-ada-002")
    temperature: float = attr.field(
        default=0.2, converter=float, validator=[validators.le(1), validators.ge(0)]
    )

    maximum_context: int | None = attr.field(
        default=None,
        metadata={
            "description": (
                "The maximum number of lines of context to include in the prompt. It is"
                " inferred automatically for openai models but you can still set it to"
                " save costs. It must be set for other models."
            )
        },
        converter=int_or_none,
        validator=validators.optional(validators.ge(0)),
    )
    parser: Parser = attr.field(  # pyright: ignore
        default="block",
        metadata={
            "description": (
                "The format for the LLM to write code in. You probably don't want to"
                " mess with this setting."
            ),
        },
        converter=parser_map.get,  # pyright: ignore
        validator=validators.instance_of(Parser),  # pyright: ignore
    )
    no_parser_prompt: bool = attr.field(
        default=False,
        metadata={
            "description": (
                "Whether to include the parser prompt in the system message. This"
                " should only be set to true for fine tuned models"
            )
        },
        converter=converters.optional(converters.to_bool),
    )

    # Context specific settings
    file_exclude_glob_list: list[str] = attr.field(
        factory=list,
        metadata={"description": "List of glob patterns to exclude from context"},
    )
    auto_context: bool = attr.field(
        default=False,
        metadata={
            "description": "Automatically select code files to include in context.",
            "abbreviation": "a",
        },
        converter=converters.optional(converters.to_bool),
    )
    auto_tokens: int = attr.field(
        default=8000,
        metadata={
            "description": "The number of tokens auto-context will add.",
        },
        converter=int,
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
    def add_fields_to_argparse(cls, parser: ArgumentParser) -> None:
        for field in attr.fields(Config):
            if "no_flag" in field.metadata:
                continue
            name = [f"--{field.name.replace('_', '-')}"]
            if "abbreviation" in field.metadata:
                name.append(f"-{field.metadata['abbreviation'].replace('_', '-')}")

            arguments = {
                "help": field.metadata.get("description", ""),
            }

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
    def create(cls, args: Namespace | None = None) -> Config:
        config = Config()

        # Each method overwrites the previous so they are in order of precedence
        config.load_file(user_config_path)
        config.load_file(get_shared_git_root_for_paths([Path(".")]) / config_file_name)

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
            stream.send(error, color="light_yellow")
        self._errors = []
