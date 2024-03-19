import asyncio
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from mentat import Mentat
from mentat.config import Config


@pytest.mark.asyncio
@patch("requests.get")
async def test_display_new_version_splash_message(mock_get):
    mock_response_version = MagicMock()
    mock_response_version.status_code = 200
    mock_response_version.json.return_value = {"info": {"version": "99.0.0"}}
    mock_response_changelog = MagicMock()
    mock_response_changelog.status_code = 200
    mock_response_changelog.text = dedent(
        """\
            Changelog
            =========

            release 99.0.0
            --------------
            - feature 1
            - feature 2
            - feature 3

            release 98.0.0
            --------------
            - feature 1"""
    )
    mock_get.side_effect = [mock_response_version, mock_response_changelog]

    mentat = Mentat()
    await mentat.startup()
    await asyncio.sleep(0.01)
    upgrade_splash_message = dedent(
        """\
        Version v99.0.0 of Mentat is available. If pip was used to install Mentat, upgrade with:
        pip install --upgrade mentat
        Upgrade for the following features/improvements:
        - feature 1
        - feature 2
        - feature 3"""
    )

    assert upgrade_splash_message in mentat._accumulated_message
    await mentat.shutdown()


@pytest.mark.asyncio
@patch("requests.get")
async def test_not_display_new_version_splash_message(mock_get):
    mock_response_version = MagicMock()
    mock_response_version.status_code = 200
    mock_response_version.json.return_value = {"info": {"version": "0.0.1"}}
    mock_response_changelog = MagicMock()
    mock_response_changelog.status_code = 200
    mock_get.side_effect = [mock_response_version]

    mentat = Mentat()
    await mentat.startup()
    await asyncio.sleep(0.01)

    assert "of Mentat is available" not in mentat._accumulated_message
    assert "Upgrade for the following features/improvements:" not in mentat._accumulated_message
    await mentat.shutdown()


@pytest.mark.asyncio
async def test_check_model():
    mentat = Mentat(config=Config(model="test"))

    await mentat.startup()
    await asyncio.sleep(0.01)
    assert "Warning: Mentat has only been tested on GPT-4" in mentat._accumulated_message
    assert "Warning: Mentat does not know how to calculate costs or context" in mentat._accumulated_message
    await mentat.shutdown()

    mentat = Mentat(config=Config(model="gpt-3.5"))

    await mentat.startup()
    await asyncio.sleep(0.01)
    assert "Warning: Mentat has only been tested on GPT-4" in mentat._accumulated_message
    assert "Warning: Mentat does not know how to calculate costs or context" not in mentat._accumulated_message
    await mentat.shutdown()

    mentat = Mentat(config=Config(model="gpt-4"))

    await mentat.startup()
    await asyncio.sleep(0.01)
    assert "Warning: Mentat has only been tested on GPT-4" not in mentat._accumulated_message
    assert "Warning: Mentat does not know how to calculate costs or context" not in mentat._accumulated_message
    await mentat.shutdown()
