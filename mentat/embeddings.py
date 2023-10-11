import numpy as np

from .llm_api import count_tokens, call_embedding_api
from .code_file import CodeFile
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


async def get_feature_similarity_scores(prompt: str, features: list[CodeFile]) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    global database
    
    # Get a list of checksum/content to fetch embeddings for
    embed_items = dict[str, str]()  # {checksum: content}
    prompt_checksum = sha256(prompt)
    if prompt_checksum not in database:
        embed_items[prompt_checksum] = prompt
    for feature in features:
        feature_checksum = feature.get_checksum()
        if feature_checksum not in database:
            feature_content = await feature.get_code_message()
            embed_items[feature_checksum] = "\n".join(feature_content)

    # Batch and process
    token_counts = {k: count_tokens(v, EMBEDDING_MODEL) for k, v in embed_items.items()}
    batches = _batch_ffd(token_counts, EMBEDDING_MAX_TOKENS)
    for batch in batches:
        batch_content = [embed_items[k] for k in batch]
        response = call_embedding_api(batch_content, EMBEDDING_MODEL)
        for k, v in zip(batch, response):
            database[k] = v

    # Calculate similarity score for each feature
    prompt_embedding = database[prompt_checksum]
    feature_embeddings = {k: database[k] for k in embed_items.keys() if k != prompt_checksum}
    similarity_scores = dict[str, float]()
    for k, v in feature_embeddings.items():
        similarity_scores[k] = _cosine_similarity(prompt_embedding, v)

    return [similarity_scores[k] for k in feature_embeddings.keys()]
