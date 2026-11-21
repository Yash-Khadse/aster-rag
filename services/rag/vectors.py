"""Dense index adapters. Every query is restricted to SQL-authorized chunk IDs."""

import atexit
import math
import os
import threading
import uuid
from functools import lru_cache

from .embeddings import embed_texts, index_signature

_lock = threading.RLock()


def _point_id(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


@lru_cache(maxsize=4)
def _qdrant(path: str):
    from qdrant_client import QdrantClient

    client = QdrantClient(location=":memory:") if path == ":memory:" else QdrantClient(path=path)
    atexit.register(client.close)
    return client


@lru_cache(maxsize=2)
def _pinecone(key: str, index: str):
    from pinecone import Pinecone

    if not key or not index:
        raise ValueError("PINECONE_API_KEY and PINECONE_INDEX are required")
    return Pinecone(api_key=key).Index(index)


def _backend():
    name = os.getenv("VECTOR_BACKEND", "qdrant")
    if name == "qdrant":
        return name, _qdrant(os.getenv("QDRANT_PATH", "data/qdrant"))
    if name == "pinecone":
        return name, _pinecone(os.getenv("PINECONE_API_KEY", ""), os.getenv("PINECONE_INDEX", ""))
    raise ValueError("VECTOR_BACKEND must be qdrant or pinecone")


def _namespace(namespace: str, signature: str | None = None) -> str:
    return f"{namespace}:{signature or index_signature()}"


def index_chunks(namespace: str, chunks: list[dict]) -> None:
    if not chunks:
        return
    if all(c.get("embedding") is not None for c in chunks):
        vectors = [c["embedding"] for c in chunks]
        dimension = int(os.getenv("EMBEDDING_DIMENSION", "384"))
        if any(len(v) != dimension or not all(math.isfinite(float(x)) for x in v) for v in vectors):
            raise ValueError("Invalid precomputed embedding dimension or values")
    else:
        vectors = embed_texts([c["text"] for c in chunks])
    name, client = _backend()
    ns = _namespace(namespace)
    if name == "pinecone":
        for start in range(0, len(chunks), 100):
            client.upsert(
                namespace=ns,
                vectors=[
                    {
                        "id": c["id"],
                        "values": v,
                        "metadata": {
                            "chunk_id": c["id"],
                            "document_id": c["document_id"],
                            "signature": index_signature(),
                        },
                    }
                    for c, v in zip(chunks[start : start + 100], vectors[start : start + 100], strict=True)
                ],
            )
    else:
        from qdrant_client import models

        collection = f"chunks_{index_signature()}"
        with _lock:
            if not client.collection_exists(collection):
                client.create_collection(
                    collection,
                    vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE),
                )
            client.upsert(
                collection,
                points=[
                    models.PointStruct(
                        id=_point_id(ns + c["id"]),
                        vector=v,
                        payload={"namespace": ns, "chunk_id": c["id"], "document_id": c["document_id"]},
                    )
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )


def dense_search(
    namespace: str, query: list[float], allowed_ids: list[str], top_k: int
) -> list[tuple[str, float]]:
    if not allowed_ids:
        return []
    if len(allowed_ids) > 10000:
        raise ValueError("Authorized corpus exceeds demo query budget")
    name, client = _backend()
    ns = _namespace(namespace)
    if name == "pinecone":
        # IDs are encoded into per-request filter via document-free ID fetch metadata below.
        # Pinecone queries cannot filter by record ID: use the chunk_id metadata field.
        response = client.query(
            namespace=ns,
            vector=query,
            top_k=top_k,
            filter={"chunk_id": {"$in": allowed_ids}},
            include_metadata=False,
        )
        return [(m.id, float(m.score)) for m in response.matches if m.id in set(allowed_ids)]
    from qdrant_client import models

    collection = f"chunks_{index_signature()}"
    with _lock:
        if not client.collection_exists(collection):
            return []
        response = client.query_points(
            collection,
            query=query,
            limit=top_k,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(key="namespace", match=models.MatchValue(value=ns)),
                    models.FieldCondition(key="chunk_id", match=models.MatchAny(any=allowed_ids)),
                ]
            ),
        )
    return [(p.payload["chunk_id"], float(p.score)) for p in response.points]


def delete_vectors(namespace: str, ids: list[str], signature: str | None = None) -> None:
    if not ids:
        return
    name, client = _backend()
    ns = _namespace(namespace, signature)
    if name == "pinecone":
        for start in range(0, len(ids), 500):
            client.delete(namespace=ns, ids=ids[start : start + 500])
    else:
        from qdrant_client import models

        collection = f"chunks_{signature or index_signature()}"
        with _lock:
            if client.collection_exists(collection):
                client.delete(
                    collection, points_selector=models.PointIdsList(points=[_point_id(ns + i) for i in ids])
                )
