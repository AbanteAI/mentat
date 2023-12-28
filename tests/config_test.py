import argparse
from pathlib import Path
from textwrap import dedent

import pytest

import mentat.config
from mentat.config import update_config
from mentat.parsers.replacement_parser import ReplacementParser
from pathlib import Path
import pytest
import yaml
from mentat import config
from unittest.mock import patch
from unittest.mock import MagicMock
from io import StringIO
from yaml import dump
import os

from mentat.utils import dd


@pytest.fixture
def mock_open(mocker):
    mock_open = mocker.patch('builtins.open', new_callable=MagicMock)
    return mock_open

@pytest.mark.asyncio
async def test_load_yaml(mock_open):
    data = {'test_key': 'test_value'}
    mock_open.return_value.__enter__.return_value = StringIO(yaml.dump(data))
    assert config.load_yaml('test_path') == data
    mock_open.assert_called_with('test_path', 'r')

@pytest.mark.asyncio
async def test_merge_configs():
    original = {'key1': 'value1', 'key2': 'value2'}
    new = {'key2': 'new_value2', 'key3': 'new_value3'}
    merged = config.merge_configs(original, new)
    assert merged == {'key1': 'value1', 'key2': 'new_value2', 'key3': 'new_value3'}


@pytest.mark.asyncio
async def test_default_config():
    "This test verifies that a config is created with default settings required for the run."
    config = mentat.user_session.get("config")

    assert config.ai.model == "gpt-4-1106-preview"
    assert config.ai.maximum_context == None

    assert config.run.auto_tokens == 8000
    assert config.run.auto_context == False

    assert config.ui.input_style == [["", "#9835bd"],
                                            ["prompt", "#ffffff bold"],
                                            ["continuation", "#ffffff bold"]]

    assert config.parser.parser_type == 'block'



@pytest.mark.asyncio
async def test_update_config():
    "This test verifies that a config is created with default settings required for the run."
    config = mentat.user_session.get("config")

    #assert that default settings are in place before we change them.
    assert config.ai.model == "gpt-4-1106-preview"
    assert config.ai.maximum_context == None

    session_config = {
        'model': 'abc-123',
        'maximum_context': 16000
    }

    update_config(session_config)

    assert config.config.ai.model == "abc-123"
    assert config.config.ai.maximum_context == 16000




