from unittest.mock import AsyncMock

import pytest

from mentat.auto_context import (
    GreedyFeatureSelector,
    LLMFeatureSelector,
    get_feature_selector,
)
from mentat.code_feature import CodeFeature, CodeMessageLevel


def test_get_feature_selector():
    s1 = get_feature_selector(use_llm=False)
    assert isinstance(s1, GreedyFeatureSelector)
    s2 = get_feature_selector(use_llm=True)
    assert isinstance(s2, LLMFeatureSelector)


@pytest.mark.asyncio
async def test_greedy_feature_selector(temp_testbed, mock_session_context):
    all_features = [
        CodeFeature(
            temp_testbed / "multifile_calculator" / "calculator.py"
        ),  # 188 tokens
        CodeFeature(
            temp_testbed / "multifile_calculator" / "operations.py"
        ),  # 87 tokens
    ]

    # No levels provided: take it or leave it
    selector = GreedyFeatureSelector()
    selected = await selector.select(all_features, 100)
    assert len(selected) == 1
    assert selected[0].path.name == "operations.py"

    selected = await selector.select(all_features, 200)
    assert len(selected) == 1
    assert selected[0].path.name == "calculator.py"

    # If levels are provided, take the largest one that fits.
    selected = await selector.select(
        all_features, 100, levels=[CodeMessageLevel.FILE_NAME]
    )
    assert len(selected) == 2
    assert selected[0].level.key == "file_name"
    assert selected[1].level.key == "code"


@pytest.mark.asyncio
async def test_llm_feature_selector(
    mocker, temp_testbed, mock_session_context, mock_setup_api_key
):
    all_features = [
        CodeFeature(
            temp_testbed / "multifile_calculator" / "calculator.py"
        ),  # 188 tokens
        CodeFeature(
            temp_testbed / "multifile_calculator" / "operations.py"
        ),  # 87 tokens
    ]

    mock_completion = mocker.patch(
        "mentat.auto_context.LLMFeatureSelector.call_llm_api", new_callable=AsyncMock
    )
    mock_completion.return_value = '["multifile_calculator/operations.py"]'

    selector = LLMFeatureSelector()
    selected = await selector.select(all_features, 100, user_prompt="test prompt")

    model, messages = mock_completion.call_args.args
    assert messages[0]["content"].startswith("You are part of")
    assert "User Query:\ntest prompt\n\nCode Files:" in messages[1]["content"]

    # Both files send to llm
    assert all(
        f.path.relative_to(temp_testbed).as_posix() in messages[1]["content"]
        for f in all_features
    )

    # Only one file returned
    assert len(selected) == 1
