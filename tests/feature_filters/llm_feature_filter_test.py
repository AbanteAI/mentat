from unittest.mock import AsyncMock

import pytest

from mentat.code_feature import CodeFeature
from mentat.feature_filters.llm_feature_filter import LLMFeatureFilter


@pytest.mark.asyncio
async def test_llm_feature_filter(
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
        "mentat.feature_filters.llm_feature_filter.call_llm_api_sync",
        new_callable=AsyncMock,
    )
    mock_completion.return_value = '["multifile_calculator/operations.py"]'

    feature_filter = LLMFeatureFilter(100, user_prompt="test prompt")
    selected = await feature_filter.filter(all_features)

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
