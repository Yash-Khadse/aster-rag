"""Binary relevance metrics; duplicate hits never inflate a score."""

import math


def retrieval_metrics(retrieved: list[str], relevant: list[str], k: int) -> dict:
    if k <= 0:
        raise ValueError("k must be positive")
    truth = set(relevant)
    if not truth:
        return {"recall": None, "precision": None, "mrr": None, "ndcg": None, "hit_rate": None}
    seen = set()
    gains = []
    for item in retrieved[:k]:
        gains.append(int(item in truth and item not in seen))
        seen.add(item)
    hits = sum(gains)
    dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(k, len(truth))))
    return {
        "recall": hits / len(truth),
        "precision": hits / k,
        "mrr": next((1 / (rank + 1) for rank, gain in enumerate(gains) if gain), 0.0),
        "ndcg": dcg / ideal,
        "hit_rate": float(hits > 0),
    }


def answer_checks(case: dict, answer: str | None = None, status: str | None = None) -> dict:
    """Answer-level golden checks; `not_run` when no generated answer exists. `status` is the generator's own."""
    checks = {}
    if case.get("expect_abstention"):
        checks["abstention"] = "not_run" if answer is None else "pass" if status == "abstained" else "fail"
    if case.get("forbidden_answer"):
        leaked = answer is not None and case["forbidden_answer"].lower() in answer.lower()
        checks["forbidden_answer"] = "not_run" if answer is None else "fail" if leaked else "pass"
    return checks


def aggregate(rows: list[dict]) -> dict:
    result = {}
    for key in ("recall", "precision", "mrr", "ndcg", "hit_rate"):
        values = [row[key] for row in rows if row.get(key) is not None]
        result[key] = sum(values) / len(values) if values else None
    return result
