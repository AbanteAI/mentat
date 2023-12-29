import argparse
import os
from io import StringIO
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
import yaml
from yaml import dump

import mentat.config
from mentat import config
from mentat.config import update_config
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.utils import dd


@pytest.fixture
def mock_open(mocker):
    mock_open = mocker.patch("builtins.open", new_callable=MagicMock)
    return mock_open


@pytest.mark.asyncio
async def test_load_yaml(mock_open):
    data = {"test_key": "test_value"}
    mock_open.return_value.__enter__.return_value = StringIO(yaml.dump(data))
    assert config.load_yaml("test_path") == data
    mock_open.assert_called_with("test_path", "r")


@pytest.mark.asyncio
async def test_default_config():
    "This test verifies that a config is created with default settings required for the run."
    config = mentat.user_session.get("config")

    assert config.ai.model == "gpt-4-1106-preview"
    assert config.ai.maximum_context == 16000

    assert config.run.auto_tokens == 8000
    assert config.run.auto_context == False

    assert config.parser.parser_type == "block"
