from pathlib import Path

import pytest

from mentat.code_feature import CodeFeature
from mentat.embeddings import get_feature_similarity_scores


def _make_code_feature(path, text):
    with open(path, "w") as f:
        f.write(text)
    return CodeFeature(path)


@pytest.mark.asyncio
async def test_get_feature_similarity_scores(mocker, mock_call_embedding_api):
    prompt = "example prompt"
    features = [
        _make_code_feature(Path(f"file{i}.txt").resolve(), f"File {i}")
        for i in range(3)
    ]
    mock_call_embedding_api.set_embedding_values(
        [
            [0.7, 0.7, 0.7],  # The prompt
            [0.4, 0.4, 0.4],
            [0.5, 0.6, 0.7],
            [0.69, 0.7, 0.71],
        ]
    )
    result = await get_feature_similarity_scores(prompt, features)
    assert len(result) == 3
    assert max(result) == result[0]  # The first feature is most similar
