# Hybrid retrieval

```mermaid
flowchart LR
  Q[Question] --> Dense[Query embedding + vector search]
  Q --> Sparse[BM25 over authorized chunks]
  Dense --> RRF[Reciprocal rank fusion]
  Sparse --> RRF
  RRF --> Dedup[Deduplicate candidates]
  Dedup --> Rerank[Optional cross-encoder]
  Rerank --> Evidence[Top-k bounded evidence]
  Evidence --> Generate[Grounded generation + validated citations]
```

Supported benchmark variants are `dense`, `bm25`, `hybrid` and `rerank` (hybrid plus cross-encoder). RRF combines reciprocal ranks; it does not add raw dense similarity to BM25 scores. SQL authorization precedes all ranking. Debug output exposes candidates, evidence and timings.

Run `uv run --extra evaluation python -m services.evaluation.benchmark --strategies bm25`. For all variants install `--extra reranking`. Corpus-level relevance is evaluated by document ID; duplicate chunks cannot inflate metrics. This small fictional corpus tests mechanics and targeted scenarios, not general enterprise retrieval quality.
