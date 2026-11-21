"""Local ONNX embeddings; deterministic hashing is restricted to explicit tests."""

import hashlib
import math
import os
import re
from functools import lru_cache


def model_id() -> str:
    return os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


@lru_cache(maxsize=2)
def _model(name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(
        model_name=name,
        threads=int(os.getenv("EMBEDDING_THREADS", "2")),
        cache_dir=os.getenv("MODEL_CACHE_DIR", "data/models"),
    )


def embed_texts(texts: list[str], query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    provider = os.getenv("EMBEDDING_PROVIDER", "fastembed")
    dimension = int(os.getenv("EMBEDDING_DIMENSION", "384"))
    if provider == "test_hash":
        if os.getenv("APP_ENV", "local") != "test":
            raise ValueError("test_hash embeddings are restricted to APP_ENV=test")
        vectors = []
        for text in texts:
            vector = [0.0] * dimension
            for token in re.findall(r"\w+", text.casefold()):
                digest = hashlib.sha256(token.encode()).digest()
                vector[int.from_bytes(digest[:4], "big") % dimension] += 1.0
            length = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / length for v in vector])
    elif provider == "fastembed":
        model = _model(model_id())
        encode = model.query_embed if query else model.passage_embed
        vectors = [v.tolist() for v in encode(texts, batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")))]
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")
    if any(len(v) != dimension or not all(math.isfinite(n) for n in v) for v in vectors):
        raise ValueError("Embedding dimension/model mismatch; create a new index and reindex")
    return vectors


def index_signature() -> str:
    value = f"{os.getenv('EMBEDDING_PROVIDER', 'fastembed')}:{model_id()}:{os.getenv('EMBEDDING_DIMENSION', '384')}"
    return hashlib.sha256(value.encode()).hexdigest()[:16]
