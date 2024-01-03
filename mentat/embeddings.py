import json
import os
import sqlite3
from pathlib import Path
from timeit import default_timer

import numpy as np

from mentat.code_feature import CodeFeature, count_feature_tokens
from mentat.errors import MentatError
from mentat.llm_api_handler import (
    count_tokens,
    model_context_size,
    model_price_per_1000_tokens,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import mentat_dir_path, sha256

EMBEDDINGS_API_BATCH_SIZE = 2048


class EmbeddingsDatabase:
    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or mentat_dir_path
        os.makedirs(self.output_dir, exist_ok=True)
        self.path = Path(self.output_dir) / "embeddings.sqlite3"
        self._connect()

    def _connect(self):
        self.conn = sqlite3.connect(self.path)
        with self.conn as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(checksum TEXT PRIMARY KEY, vector BLOB)"
            )

    def set(self, items: dict[str, list[float]]):
        with self.conn as db:
            db.executemany(
                "INSERT OR REPLACE INTO embeddings (checksum, vector) VALUES (?, ?)",
                [
                    (key, sqlite3.Binary(json.dumps(value).encode("utf-8")))
                    for key, value in items.items()
                ],
            )

    def get(self, keys: list[str]) -> dict[str, list[float]]:
        with self.conn as db:
            cursor = db.execute(
                "SELECT checksum, vector FROM embeddings WHERE checksum IN"
                f" ({','.join(['?']*len(keys))})",
                keys,
            )
            return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

    def exists(self, key: str) -> bool:
        with self.conn as db:
            cursor = db.execute("SELECT 1 FROM embeddings WHERE checksum=?", (key,))
            return cursor.fetchone() is not None

    def __del__(self):
        self.conn.close()


database = EmbeddingsDatabase()


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate the cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    return dot_product / (norm_v1 * norm_v2)  # pyright: ignore


async def get_feature_similarity_scores(
    prompt: str,
    features: list[CodeFeature],
    loading_multiplier: float = 0.0,
) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    global database
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    cost_tracker = session_context.cost_tracker
    embedding_model = session_context.config.embedding_model
    llm_api_handler = session_context.llm_api_handler

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

    prompt_checksum = sha256(prompt)
    checksums: list[str] = [f.get_checksum() for f in features]
    tokens: list[int] = await count_feature_tokens(features, embedding_model)
    embed_texts = list[str]()
    embed_checksums = list[str]()
    embed_tokens = list[int]()
    if not database.exists(prompt_checksum):
        embed_texts.append(prompt)
        embed_checksums.append(prompt_checksum)
        embed_tokens.append(prompt_tokens)
    for feature, checksum, token in zip(features, checksums, tokens):
        if token > max_model_tokens:
            continue
        if not database.exists(checksum):
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

    # Fetch embeddings in batches
    if len(embed_texts) == 0:
        n_batches = 0
    else:
        n_batches = len(embed_texts) // EMBEDDINGS_API_BATCH_SIZE + 1
    for batch in range(n_batches):
        if loading_multiplier:
            stream.send(
                f"Fetching embeddings, batch {batch+1}/{n_batches}",
                channel="loading",
                progress=(100 / n_batches) * loading_multiplier,
            )
        start_time = default_timer()
        i_start, i_end = (
            batch * EMBEDDINGS_API_BATCH_SIZE,
            (batch + 1) * EMBEDDINGS_API_BATCH_SIZE,
        )
        _texts = embed_texts[i_start:i_end]
        _checksums = embed_checksums[i_start:i_end]
        _tokens = embed_tokens[i_start:i_end]

        response = await llm_api_handler.call_embedding_api(_texts, embedding_model)
        cost_tracker.log_api_call_stats(
            sum(_tokens),
            0,
            embedding_model,
            start_time - default_timer(),
        )
        database.set({k: v for k, v in zip(_checksums, response)})

    # Calculate similarity score for each feature
    prompt_embedding = database.get([prompt_checksum])[prompt_checksum]
    embeddings = database.get(checksums)
    scores = [
        _cosine_similarity(prompt_embedding, embeddings[k]) if k in embeddings else 0.0
        for k in checksums
    ]

    return scores
