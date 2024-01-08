import os
from timeit import default_timer
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from chromadb.api.types import Where

from mentat.code_feature import CodeFeature, count_feature_tokens
from mentat.errors import MentatError
from mentat.llm_api_handler import (
    count_tokens,
    model_context_size,
    model_price_per_1000_tokens,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import mentat_dir_path

client = chromadb.PersistentClient(path=str(mentat_dir_path / "chroma"))


"""
TODO: Add a migration script
1. Check for mentat_dir_path / embeddings.sqlite3
2. If found, add everything from it to the database

Chroma saves the texts by default, but our old EmbeddingsDatabase did not, so
these migrated records will be missing the 'document' field, which shouldn't
cause any problems. If it does in the future, we can update 'exists' to return 
false if the id exists but the 'document' is missing.
"""


THRESHOLD = 10
def create_query(checksums: list[str]) -> Where:
    if len(checksums) <= THRESHOLD:
        return {"$or": [{"checksum": c} for c in checksums]}
    else:
        mid = len(checksums) // 2
        left_query = create_query(checksums[:mid])
        right_query = create_query(checksums[mid:])
        return {"$or": [left_query, right_query]}


class Collection:
    _collection = None

    def __init__(self, embedding_model: str):
        api_key = os.getenv("OPENAI_API_KEY")
        embedding_function = OpenAIEmbeddingFunction(
            api_key=api_key, model_name=embedding_model
        )
        self._collection = client.get_or_create_collection(
            name=f"mentat-{embedding_model}",
            # TODO: The default (l2) is more efficient, but lower is better
            metadata={"hnsw:space": "cosine"},
            # TODO: Chromadb supports images, but ada doesn't
            embedding_function=embedding_function,  # type: ignore
        )

    def exists(self, id: str) -> bool:
        assert self._collection is not None, "Collection not initialized"
        return len(self._collection.get(id)["ids"]) > 0

    def add(self, checksums: list[str], texts: list[str]) -> None:
        assert self._collection is not None, "Collection not initialized"
        return self._collection.add(  # type: ignore
            ids=checksums,
            documents=texts,
            metadatas=[{"checksum": c} for c in checksums],
        )

    def query(self, prompt: str, checksums: list[str]) -> dict[str, float]:
        assert self._collection is not None, "Collection not initialized"
        results = self._collection.query(  # type: ignore
            query_texts=[prompt],
            where=create_query(checksums),
            n_results=len(checksums),
        )
        assert results["distances"], "Error calculating distances"
        return {c: e for c, e in zip(results["ids"][0], results["distances"][0])}


async def get_feature_similarity_scores(
    prompt: str,
    features: list[CodeFeature],
    loading_multiplier: float = 0.0,
) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    cost_tracker = session_context.cost_tracker
    embedding_model = session_context.config.embedding_model

    collection = Collection(embedding_model)
    features = features[:250]

    # TODO: How does chroma handle oversized files?
    max_model_tokens = model_context_size(embedding_model)
    if max_model_tokens is None:
        raise MentatError(f"Missing model context size for {embedding_model}.")
    prompt_tokens = count_tokens(prompt, embedding_model, False)
    if prompt_tokens > max_model_tokens:
        stream.send(
            f"Warning: Prompt contains {prompt_tokens} tokens, but the model"
            f" can only handle {max_model_tokens} tokens. Ignoring embeddings."
        )
        return [0.0 for _ in features]

    checksums: list[str] = [f.get_checksum() for f in features]
    tokens: list[int] = await count_feature_tokens(features, embedding_model)
    embed_texts = list[str]()
    embed_checksums = list[str]()
    embed_tokens = list[int]()
    for feature, checksum, token in zip(features, checksums, tokens):
        if token > max_model_tokens:
            continue
        if not collection.exists(checksum) and checksum not in embed_checksums:
            embed_texts.append("\n".join(feature.get_code_message()))
            embed_checksums.append(checksum)
            embed_tokens.append(token)

    # If it costs more than $1, get confirmation from user.
    cost = model_price_per_1000_tokens(embedding_model)
    if cost is None:
        stream.send(
            "Warning: Could not determine cost of embeddings. Continuing anyway.",
            style="warning",
        )
    else:
        expected_cost = (sum(embed_tokens) / 1000) * cost[0]
        if expected_cost > 1.0:
            stream.send(
                f"Embedding {sum(embed_tokens)} tokens will cost ${cost[0]:.2f}."
                " Continue anyway?"
            )
            if not await ask_yes_no(default_yes=True):
                stream.send("Ignoring embeddings for now.")
                return [0.0 for _ in checksums]

    if embed_texts:
        start_time = default_timer()
        if loading_multiplier:
            stream.send(
                f"Fetching embeddings for {len(embed_texts)} documents", 
                channel="loading", 
                progress=50 * loading_multiplier,
            )
        collection.add(embed_checksums, embed_texts)
        cost_tracker.log_api_call_stats(
            sum(embed_tokens),
            0,
            embedding_model,
            start_time - default_timer(),
        )

    if loading_multiplier:
        stream.send(
            "Matching relevant documents based on embedding similarity",
            channel="loading",
            progress=(50 if embed_texts else 100) * loading_multiplier,
        )
    scores = collection.query(prompt, checksums)
    return [scores[c] for c in checksums]
