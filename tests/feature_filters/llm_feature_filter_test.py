import pytest

from mentat.code_feature import CodeFeature
from mentat.feature_filters.llm_feature_filter import LLMFeatureFilter


@pytest.mark.asyncio
async def test_llm_feature_filter(mocker, temp_testbed, mock_call_llm_api, mock_session_context):
    all_features = [
        CodeFeature(temp_testbed / "multifile_calculator" / "calculator.py"),  # 188 tokens
        CodeFeature(temp_testbed / "multifile_calculator" / "operations.py"),  # 87 tokens
    ]

    mock_call_llm_api.set_unstreamed_values('{"multifile_calculator/operations.py": "test reason"}')
    mock_session_context.config.llm_feature_filter = 10000

    feature_filter = LLMFeatureFilter(100, user_prompt="test prompt")
    selected = await feature_filter.filter(all_features)

    messages = mock_call_llm_api.call_args.kwargs["messages"]
    assert messages[0]["content"].startswith("You are part of")
    assert messages[1]["content"].startswith("CODE FILES")
    assert messages[2]["content"].startswith("USER QUERY")
    assert messages[3]["content"].startswith("Now,")

    # Only one file returned
    assert len(selected) == 1
