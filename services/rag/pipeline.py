"""Stable service boundary consumed by API, workers and evaluations."""

from .embeddings import embed_texts, index_signature
from .generation import generate_answer
from .parsing import chunk_pages, parse_document
from .retrieval import contextual_query, retrieve
from .vectors import delete_vectors, index_chunks

__all__ = [
    "chunk_pages",
    "contextual_query",
    "delete_vectors",
    "embed_texts",
    "generate_answer",
    "index_chunks",
    "index_signature",
    "parse_document",
    "retrieve",
]
