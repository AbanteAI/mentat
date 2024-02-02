from timeit import default_timer

import chromadb
from chromadb.api.types import Embeddable, EmbeddingFunction, Embeddings

from mentat.code_feature import CodeFeature, count_feature_tokens
from mentat.errors import MentatError
from mentat.llm_api_handler import model_context_size, model_price_per_1000_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import mentat_dir_path

EMBEDDINGS_API_BATCH_SIZE = 2048

client = chromadb.PersistentClient(path=str(mentat_dir_path / "chroma"))


class MentatEmbeddingFunction(EmbeddingFunction[Embeddable]):
    def __call__(self, input: Embeddable) -> Embeddings:
        if not all(isinstance(item, str) for item in input):
            raise MentatError("MentatEmbeddings only enabled for text files")
        session_context = SESSION_CONTEXT.get()
        config = session_context.config
        llm_api_handler = session_context.llm_api_handler

        n_batches = (
            0 if len(input) == 0 else len(input) // EMBEDDINGS_API_BATCH_SIZE + 1
        )
        output: Embeddings = []
        for batch in range(n_batches):
            i_start, i_end = (
                batch * EMBEDDINGS_API_BATCH_SIZE,
                (batch + 1) * EMBEDDINGS_API_BATCH_SIZE,
            )
            response = llm_api_handler.call_embedding_api(
                input[i_start:i_end], config.embedding_model
            )
            output += response
        return output


class Collection:
    def __init__(self, embedding_model: str):
        self._collection = client.get_or_create_collection(
            name=f"mentat-{embedding_model}",
            embedding_function=MentatEmbeddingFunction(),
        )

    def exists(self, id: str) -> bool:
        assert self._collection is not None, "Collection not initialized"
        return len(self._collection.get(id)["ids"]) > 0

    def add(self, checksums: list[str], texts: list[str]) -> None:
        assert self._collection is not None, "Collection not initialized"
        return self._collection.add(  # type: ignore
            ids=checksums,
            documents=texts,
            metadatas=[{"active": False} for _ in checksums],
        )

    def query(self, prompt: str, checksums: list[str]) -> dict[str, float]:
        assert self._collection is not None, "Collection not initialized"

        self._collection.update(  # type: ignore
            ids=checksums,
            metadatas=[{"active": True} for _ in checksums],
        )
        results = self._collection.query(  # type: ignore
            query_texts=[prompt],
            where={"active": True},
            n_results=len(checksums) + 1,
        )
        self._collection.update(  # type: ignore
            ids=checksums,
            metadatas=[{"active": False} for _ in checksums],
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
    config = session_context.config
    cost_tracker = session_context.cost_tracker
    embedding_model = session_context.config.embedding_model

    max_model_tokens = model_context_size(config.embedding_model)
    if max_model_tokens is None:
        raise MentatError(f"Missing model context size for {embedding_model}.")

    # Initialize DB
    collection = Collection(embedding_model)

    # Identify which items need embeddings.
    checksums: list[str] = [f.get_checksum() for f in features]
    tokens: list[int] = await count_feature_tokens(features, embedding_model)
    embed_texts = list[str]()
    embed_checksums = list[str]()
    embed_tokens = list[int]()
    for feature, checksum, token in zip(features, checksums, tokens):
        if token > max_model_tokens:
            stream.send(
                f"Warning: Feature {str(feature)} has {token} tokens, which exceeds the"
                f" maximum of {max_model_tokens} for model {config.embedding_model}."
                " Skipping."
            )
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

    # Load embeddings
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

    # Get similarity scores
    if loading_multiplier:
        stream.send(
            "Matching relevant documents based on embedding similarity",
            channel="loading",
            progress=(50 if embed_texts else 100) * loading_multiplier,
        )
    _checksums = list(set(checksums))
    scores = collection.query(prompt, _checksums)
    return [scores.get(f.get_checksum(), 0) for f in features]
