import asyncio

import numpy as np

from .code_file import CodeFile
from .llm_api import call_embedding_api, count_tokens
from .utils import sha256

EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_MAX_TOKENS = 8192


database = dict[str, list[float]]()


def _batch_ffd(data: dict[str, int], batch_size: int) -> list[list[str]]:
    """Batch files using the First Fit Decreasing algorithm."""
    # Sort the data by the length of the strings in descending order
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
    batches = list[list[str]]()
    for key, value in sorted_data:
        # Place each item in the first batch that it fits in
        placed = False
        for batch in batches:
            if sum(data[k] for k in batch) + value <= batch_size:
                batch.append(key)
                placed = True
                break
        if not placed:
            batches.append([key])
    return batches


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate the cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    return dot_product / (norm_v1 * norm_v2)


async def _count_feature_tokens(features: list[CodeFile], model: str) -> list[int]:
    """Return the number of tokens in each feature."""
    sem = asyncio.Semaphore(10)

    async def _count_tokens(feature: CodeFile) -> int:
        async with sem:
            return await feature.count_tokens(model)

    tasks = [_count_tokens(f) for f in features]
    return await asyncio.gather(*tasks)


async def get_feature_similarity_scores(
    prompt: str, features: list[CodeFile]
) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    assert all([isinstance(f, CodeFile) for f in features]), "Invalid feature list"
    global database

    # Keep things in the same order
    checksums: list[str] = [f.get_checksum() for f in features]
    tokens: list[int] = await _count_feature_tokens(features, EMBEDDING_MODEL)
    skip: list[bool] = [t > EMBEDDING_MAX_TOKENS for t in tokens]

    # Make a checksum:content dict of all items that need to be embedded
    items_to_embed = dict[str, str]()
    items_to_embed_tokens = dict[str, int]()
    prompt_checksum = sha256(prompt)
    if prompt_checksum not in database:
        items_to_embed[prompt_checksum] = prompt
        items_to_embed_tokens[prompt_checksum] = count_tokens(prompt, EMBEDDING_MODEL)
    for feature, checksum, token, _skip in zip(features, checksums, tokens, skip):
        if _skip:
            continue
        if checksum not in database:
            feature_content = await feature.get_code_message()
            # Remove line numbering
            items_to_embed[checksum] = "\n".join(feature_content)
            items_to_embed_tokens[checksum] = token

    # Fetch embeddings in batches
    batches = _batch_ffd(items_to_embed_tokens, EMBEDDING_MAX_TOKENS)
    for batch in batches:
        if len(batch) == 1:
            continue
        batch_content = [items_to_embed[k] for k in batch]
        response = call_embedding_api(batch_content, EMBEDDING_MODEL)
        for k, v in zip(batch, response):
            database[k] = v

    # Calculate similarity score for each feature
    prompt_embedding = database[prompt_checksum]
    scores = [0.0 for _ in checksums]
    for i, checksum in enumerate(checksums):
        if skip[i]:
            continue
        feature_embedding = database[checksum]
        scores[i] = _cosine_similarity(prompt_embedding, feature_embedding)

    return scores
