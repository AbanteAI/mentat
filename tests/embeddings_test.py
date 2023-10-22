import pytest

from mentat.code_feature import CodeFeature
from mentat.embeddings import _batch_ffd, get_feature_similarity_scores


def test_batch_ffd():
    data = {"a": 4, "b": 5, "c": 3, "d": 2}
    batch_size = 6
    result = _batch_ffd(data, batch_size)
    expected = [["b"], ["a", "d"], ["c"]]
    assert result == expected


def _make_code_feature(path, text):
    with open(path, "w") as f:
        f.write(text)
    return CodeFeature(path)


@pytest.mark.asyncio
async def test_get_feature_similarity_scores(mocker, mock_session_context):
    prompt = "example prompt"
    features = [_make_code_feature(f"file{i}.txt", f"File {i}") for i in range(3)]
    mocker.patch(
        "mentat.embeddings.call_embedding_api",
        return_value=[
            [0.4, 0.4, 0.4],
            [0.5, 0.6, 0.7],
            [0.69, 0.7, 0.71],
            [0.7, 0.7, 0.7],  # The prompt
        ],
    )
    result = await get_feature_similarity_scores(prompt, features)
    assert len(result) == 3
    assert max(result) == result[0]  # The first feature is most similar
