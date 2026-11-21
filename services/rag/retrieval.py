"""Independent lexical/dense retrieval, RRF, bounded cross-encoder and context selection."""

import math
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import lru_cache
from threading import BoundedSemaphore

from .embeddings import embed_texts
from .vectors import dense_search

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reranker")
_rerank_slot = BoundedSemaphore(1)


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:[-./][\w]+)*", text.casefold())


def estimate_tokens(text: str) -> int:
    # Conservative: word tokens x1.5 (subwords), floored by chars/4 so CJK or symbol-heavy text is not undercounted.
    return max(math.ceil(len(tokens(text)) * 1.5), math.ceil(len(text) / 4))


def lexical_search(query: str, chunks: list[dict], top_k: int) -> list[tuple[str, float]]:
    return lexical_scan(query, ((c["id"], c["text"]) for c in chunks), top_k)


def lexical_scan(query: str, texts: Iterable[tuple[str, str]], top_k: int) -> list[tuple[str, float]]:
    """BM25 over a stream of (id, text). Only (id, length, query-term counts) are retained per chunk, so
    memory is O(chunks) small tuples, never O(corpus text).

    shortcut: BM25 still has to *read* every authorized chunk's text once per query (df and average length
    are corpus-wide); upgrade to a persisted per-chunk token-count/term index (or Postgres FTS) when the
    per-query scan time matters.
    """
    # BM25 implementation keeps positive IDF even in small corpora.
    terms = sorted(set(tokens(query)))
    if not terms:
        return []
    wanted = set(terms)
    documents = []
    df: Counter[str] = Counter()
    for identifier, text in texts:
        words = tokens(text)
        counts = Counter(w for w in words if w in wanted)
        df.update(counts.keys())
        documents.append((identifier, len(words), counts))
    if not documents:
        return []
    avg_len = sum(length for _, length, _ in documents) / len(documents) or 1
    idf = {term: math.log(1 + (len(documents) - df[term] + 0.5) / (df[term] + 0.5)) for term in terms}
    scores = []
    for identifier, length, counts in documents:
        score = 0.0
        normalization = 1.5 * (0.25 + 0.75 * length / avg_len)
        for term in terms:
            frequency = counts[term]
            if frequency:
                score += idf[term] * frequency * 2.5 / (frequency + normalization)
        if score > 0:
            scores.append((identifier, score))
    return sorted(scores, key=lambda x: (-x[1], x[0]))[:top_k]


def reciprocal_rank_fusion(rankings: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("RRF constant must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen = set()
        for rank, (identifier, _) in enumerate(ranking, 1):
            if identifier not in seen:
                scores[identifier] = scores.get(identifier, 0) + 1 / (k + rank)
                seen.add(identifier)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


@lru_cache(maxsize=1)
def _cross_encoder(model: str, provider: str = "fastembed"):
    if provider == "fastembed":
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        return TextCrossEncoder(
            model_name=model, threads=2, cache_dir=os.getenv("MODEL_CACHE_DIR", "data/models")
        )
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model, device="cpu")


def _predict(query: str, candidates: list[dict]) -> list[dict]:
    try:
        provider = os.getenv("RERANKER_PROVIDER", "fastembed")
        default_model = (
            "Xenova/ms-marco-MiniLM-L-6-v2"
            if provider == "fastembed"
            else "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        model = _cross_encoder(os.getenv("RERANKER_MODEL", default_model), provider)
        scores = (
            list(model.rerank(query, [c["text"] for c in candidates]))
            if provider == "fastembed"
            else model.predict([(query, c["text"]) for c in candidates], batch_size=8)
        )
        if len(scores) != len(candidates) or not all(math.isfinite(float(x)) for x in scores):
            raise ValueError("Reranker returned invalid scores")
        return sorted(
            [{**c, "rerank_score": float(s)} for c, s in zip(candidates, scores, strict=True)],
            key=lambda c: (-c["rerank_score"], c["id"]),
        )
    finally:
        _rerank_slot.release()


def _rerank(query: str, candidates: list[dict]) -> tuple[list[dict], str, str | None]:
    """Return (ranking, status, reason). Status ending in `_fallback` keeps the baseline order; reason says why."""
    if not candidates:
        return [], "empty", None
    provider = os.getenv("RERANKER_PROVIDER", "fastembed")
    if provider == "none":
        return candidates, "disabled", None
    if provider not in {"fastembed", "cross_encoder"}:
        raise ValueError("RERANKER_PROVIDER must be fastembed, cross_encoder or none")
    if not _rerank_slot.acquire(blocking=False):
        return candidates, "busy_fallback", "another rerank is already running"
    future = _executor.submit(_predict, query, candidates)
    timeout = float(os.getenv("RERANKER_TIMEOUT_SECONDS", "15"))
    try:
        return future.result(timeout=timeout), "cross_encoder", None
    except TimeoutError:
        return candidates, "timeout_fallback", f"reranker exceeded {timeout:g}s"
    except Exception as exc:  # noqa: BLE001 -- provider failures deliberately preserve the authorized baseline ranking
        return candidates, "unavailable_fallback", f"{type(exc).__name__}: {exc}"[:200]


def rerank_candidates(query: str, candidates: list[dict]) -> tuple[list[dict], str]:
    ranked, status, _ = _rerank(query, candidates)
    return ranked, status


_FOLLOWUP = re.compile(
    r"^(what about|and (?:for|what)|how about|does (?:that|this)|what if)\b", re.IGNORECASE
)
# Short only: long pronoun/"and ..." questions are usually standalone.
_SHORT_FOLLOWUP = re.compile(
    r"^(?:and (?:who|when|where|which|why|how)|it|that|this|they|those)\b", re.IGNORECASE
)


def contextual_query(question: str, history: list[dict] | None = None) -> str:
    normalized = " ".join(question.split())
    if _FOLLOWUP.match(normalized) or (len(normalized.split()) <= 7 and _SHORT_FOLLOWUP.match(normalized)):
        previous = [m.get("content", m.get("text", "")) for m in (history or []) if m.get("role") == "user"]
        if previous:
            return f"{previous[-1][:600]}\nFollow-up: {normalized}"
    return normalized


def retrieve(
    query: str,
    chunks: list[dict],
    namespace: str,
    strategy: str = "hybrid",
    top_k: int = 5,
    rerank: bool = True,
    fetch: Callable[[list[str]], list[dict]] | None = None,
    scan: Callable[[], Iterable[tuple[str, str]]] | None = None,
) -> dict:
    """`chunks` is the ACL-authorized set; only "id" is required of each entry. Candidate generation uses ids
    (dense) and a streamed (id, text) scan (BM25, `scan`); full chunks are loaded via `fetch(ids)` only for
    the fused candidate pool. Without callbacks, `chunks` must carry "text" and is used directly."""
    if strategy not in {"dense", "bm25", "hybrid"}:
        raise ValueError("Unknown retrieval strategy")
    if not 1 <= top_k <= 20 or not query.strip() or len(query) > 4000:
        raise ValueError("Invalid query or top_k")
    started = time.perf_counter()
    timings = {}
    by_id = {c["id"]: c for c in chunks}
    candidate_k = min(100, max(top_k, int(os.getenv("RETRIEVAL_CANDIDATES", "20"))))
    dense, sparse = [], []
    if strategy in {"dense", "hybrid"} and chunks:
        tick = time.perf_counter()
        vector = embed_texts([query], query=True)[0]
        timings["embedding_ms"] = (time.perf_counter() - tick) * 1000
        tick = time.perf_counter()
        dense = dense_search(namespace, vector, list(by_id), candidate_k)
        dense = [(i, s) for i, s in dense if i in by_id and s >= float(os.getenv("MIN_DENSE_SCORE", "0.2"))]
        timings["dense_ms"] = (time.perf_counter() - tick) * 1000
    if strategy in {"bm25", "hybrid"}:
        tick = time.perf_counter()
        stream = scan() if scan else ((c["id"], c["text"]) for c in chunks)
        sparse = lexical_scan(query, ((i, t) for i, t in stream if i in by_id), candidate_k)
        timings["sparse_ms"] = (time.perf_counter() - tick) * 1000
    tick = time.perf_counter()
    ranking = (
        reciprocal_rank_fusion([dense, sparse])
        if strategy == "hybrid"
        else dense
        if strategy == "dense"
        else sparse
    )
    dense_scores, sparse_scores = dict(dense), dict(sparse)
    pool = [(i, score) for i, score in ranking[:candidate_k] if i in by_id]
    # Bounded text load: at most candidate_k (<=100) chunks, whatever the workspace size.
    loaded = {c["id"]: c for c in (fetch([i for i, _ in pool]) if fetch else (by_id[i] for i, _ in pool))}
    candidates = [
        {
            **loaded[i],
            "score": score,
            "dense_score": dense_scores.get(i),
            "sparse_score": sparse_scores.get(i),
        }
        for i, score in pool
        if i in loaded
    ]
    timings["fusion_ms"] = (time.perf_counter() - tick) * 1000
    tick = time.perf_counter()
    candidates, reranker_status, reranker_reason = (
        _rerank(query, candidates) if rerank else (candidates, "disabled", None)
    )
    timings["reranking_ms"] = (time.perf_counter() - tick) * 1000
    evidence, seen, used, used_tokens = [], set(), 0, 0
    # Default 1800 est. tokens: a 4096-token Ollama window minus prompt/history (~700) and 1200 answer tokens.
    budget = int(os.getenv("CONTEXT_TOKEN_BUDGET", "1800"))
    for candidate in candidates:
        fingerprint = candidate["text"].strip()
        cost = estimate_tokens(fingerprint)
        if fingerprint in seen or used_tokens + cost > budget:
            continue
        evidence.append(candidate)
        seen.add(fingerprint)
        used += len(fingerprint)
        used_tokens += cost
        if len(evidence) >= top_k:
            break
    timings["retrieval_ms"] = (time.perf_counter() - started) * 1000
    return {
        "evidence": evidence,
        "candidates": candidates,
        "timings": timings,
        "query": query,
        "strategy": strategy,
        # Status is one of empty/disabled/cross_encoder or a *_fallback (baseline order kept); the reason
        # is None unless a fallback happened, so callers can surface why reranking did not run.
        "reranker_status": reranker_status,
        "reranker_reason": reranker_reason,
        "reranker_fallback": reranker_status.endswith("_fallback"),
        "context_characters": used,
        "context_tokens": used_tokens,
    }
