import argparse
from pathlib import Path
from textwrap import dedent

import pytest

import mentat.config
from mentat.config import Config, config_file_name
from mentat.parsers.replacement_parser import ReplacementParser


@pytest.mark.asyncio
async def test_config_creation():
    "This test verifies the Config adds the parameters to the argparse object."
    "Those take precedence over the config files and the project config takes"
    "precedence over the user config."
    parser = argparse.ArgumentParser()
    Config.add_fields_to_argparse(parser)
    args = parser.parse_args(
        [
            "--model",
            "model",
            "--temperature",
            "0.2",
            "--maximum-context",
            "1",
            "--use-embeddings",
            "-a",
            "2",
        ]
    )
    assert args.model == "model"
    assert args.temperature == 0.2
    assert args.maximum_context == "1"
    assert args.parser is None
    assert args.use_embeddings
    assert args.auto_tokens == "2"

    with open(config_file_name, "w") as project_config_file:
        project_config_file.write(dedent("""\
        {
            "input_style": [[ "project", "yes" ]]
        }"""))

    mentat.config.user_config_path = Path(str(config_file_name) + "1")
    with open(mentat.config.user_config_path, "w") as user_config_file:
        user_config_file.write(dedent("""\
        {
            "model": "test",
            "parser": "replacement",
            "input_style": [[ "user", "yes" ]]
        }"""))

    config = Config.create(args)

    assert config.model == "model"
    assert config.temperature == 0.2
    assert config.maximum_context == 1
    assert type(config.parser) == ReplacementParser
    assert config.use_embeddings
    assert not config.no_code_map
    assert config.auto_tokens == 2
    assert config.input_style == [["project", "yes"]]


@pytest.mark.asyncio
async def test_invalid_config():
    # If invalid config file is found, it should use next config
    with open(config_file_name, "w") as project_config_file:
        project_config_file.write(dedent("""\
        {
            "model": "project",
            "format": "I have a trailing comma",
        }"""))

    mentat.config.user_config_path = Path(str(config_file_name) + "1")
    with open(mentat.config.user_config_path, "w") as user_config_file:
        user_config_file.write(dedent("""\
        {
            "model": "test",
            "foobar": "Not a real setting"
        }"""))

    config = Config.create()
    assert (
        config._errors[0]
        == "Warning: Config .mentat_config.json1 contains unrecognized setting: foobar"
    )
    assert (
        "contains invalid json; ignoring user configuration file" in config._errors[1]
    )
    assert config.model == "test"
