from copy import deepcopy

import pytest

from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.feature_filters.truncate_filter import TruncateFilter


@pytest.mark.asyncio
async def test_truncate_feature_selector(temp_testbed, mock_session_context):
    all_features = [
        CodeFeature(
            temp_testbed / "multifile_calculator" / "calculator.py"
        ),  # 188 tokens
        CodeFeature(
            temp_testbed / "multifile_calculator" / "operations.py"
        ),  # 87 tokens
    ]

    feature_filter = TruncateFilter(100)
    selected = await feature_filter.filter(deepcopy(all_features))
    assert len(selected) == 2
    assert selected[0].level == CodeMessageLevel.FILE_NAME
    assert selected[1].level == CodeMessageLevel.CODE

    feature_filter = TruncateFilter(200)
    selected = await feature_filter.filter(deepcopy(all_features))
    assert len(selected) == 2
    assert selected[0].level == CodeMessageLevel.CODE
    assert selected[1].level == CodeMessageLevel.FILE_NAME

    feature_filter = TruncateFilter(188)
    selected = await feature_filter.filter(deepcopy(all_features))
    assert len(selected) == 1
    assert selected[0].level == CodeMessageLevel.CODE

    feature_filter = TruncateFilter(100, code_map=True)
    selected = await feature_filter.filter(deepcopy(all_features))
    assert len(selected) == 2
    assert selected[0].level == CodeMessageLevel.CMAP_FULL
