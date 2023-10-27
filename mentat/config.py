from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from json import JSONDecodeError
from pathlib import Path

import attr
from attr import validators

from mentat.git_handler import get_shared_git_root_for_paths
from mentat.parsers.parser_map import parser_map
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path

config_file_name = Path(".mentat_config.json")
user_config_path = mentat_dir_path / config_file_name


def parse_bool(s: str | bool | None) -> bool:
    if isinstance(s, bool):
        return s
    if s is None:
        return False
    return s.lower() in ("true", "1", "t", "y", "yes")


def int_or_none(s: str | None) -> int | None:
    if s is not None:
        return int(s)
    return None


@attr.define
class Config:
    _errors: list[str] = attr.field(default=[])

    # Model specific settings
    model: str = attr.field(default="gpt-4-0314")
    temperature: float = attr.field(
        default=0.5, converter=float, validator=[validators.le(1), validators.ge(0)]
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
    format: str = attr.field(
        default="block",
        metadata={
            "description": (
                "The format for the LLM to write code in. You probably don't want to"
                " mess with this setting."
            ),
            "no_midsession_change": True,
        },
        validator=validators.optional(validators.in_(parser_map)),
    )

    # Context specific settings
    file_exclude_glob_list: list[str] = attr.field(
        default=[],
        metadata={"description": "List of glob patterns to exclude from context"},
    )
    use_embeddings: bool = attr.field(
        default=False,
        metadata={
            "description": "Fetch/compare embeddings to auto-generate code context"
        },
        converter=parse_bool,
    )
    no_code_map: bool = attr.field(
        default=False,
        metadata={
            "description": (
                "Exclude the file structure/syntax map from the system prompt"
            )
        },
        converter=parse_bool,
    )
    auto_tokens: int | None = attr.field(
        default=0,
        metadata={
            "description": (
                "Maximum number of auto-generated tokens to include in the prompt"
                " context"
            ),
            "abbreviation": "a",
        },
        converter=int_or_none,
        validator=validators.optional(validators.ge(0)),
    )

    # Only settable by config file
    input_style: list[tuple[str, str]] = attr.field(
        default=[
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
        for field in vars(args):
            if hasattr(self, field) and getattr(args, field) is not None:
                try:
                    setattr(self, field, getattr(args, field))
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
