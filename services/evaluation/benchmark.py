"""Run actual retrieval providers; errors are reported, never replaced by fake scores."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from services.evaluation.metrics import aggregate, answer_checks, retrieval_metrics

ROOT = Path(__file__).resolve().parents[2]


def load_dataset():
    corpus = json.loads((ROOT / "datasets/corpus.json").read_text(encoding="utf-8"))
    golden = json.loads((ROOT / "datasets/golden.json").read_text(encoding="utf-8"))
    if corpus["version"] != golden["version"]:
        raise ValueError("Corpus and golden versions differ")
    return corpus, golden


def build_chunks(corpus):
    """Every document, unchunked (one chunk per doc), with its permission/status metadata."""
    return [
        {
            **doc,
            "document_id": doc["id"],
            "page": 1,
            "section": doc["title"],
            "version": doc.get("version", 1),
            "status": "ready" if doc.get("current", True) else "superseded",
        }
        for doc in corpus["documents"]
    ]


def visible_to_member(chunk, user_id="member"):
    # Mirrors authorized_chunks/can_read in apps/api/rag_api/main.py for a plain (non-admin) member:
    # only "ready" documents that are workspace-wide, owned by the user or allow-listing them.
    if chunk["status"] != "ready":
        return False
    scope = chunk["access_scope"]
    return (
        scope == "workspace"
        or chunk.get("owner_id") == user_id
        or (scope == "restricted" and user_id in chunk.get("allowed_users", []))
    )


def forbidden_hits(retrieved_ids, case):
    return sorted(set(case.get("forbidden", [])) & set(retrieved_ids))


def run_benchmark(strategies=None, k=5, judge=False):
    from services.rag import pipeline

    corpus, golden = load_dataset()
    all_chunks = build_chunks(corpus)
    chunks = [chunk for chunk in all_chunks if visible_to_member(chunk)]
    if any(item != "bm25" for item in (strategies or ["dense"])):
        pipeline.index_chunks("benchmark", all_chunks)  # index everything; retrieval gets only visible chunks
    report = {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "dataset_version": golden["version"],
        "dataset_sha256": hashlib.sha256(json.dumps([corpus, golden], sort_keys=True).encode()).hexdigest(),
        "python": platform.python_version(),
        "top_k": k,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        "reranker_model": os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2"),
        "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "fastembed"),
        "semantic_benchmark": os.getenv("EMBEDDING_PROVIDER") != "test_hash",
        "limits": {
            "n_docs": len(all_chunks),
            "n_visible_docs": len(chunks),
            "n_questions": len(golden["cases"]),
            "chunked": False,
        },
        "variants": [],
        "judge": {"status": "not_run", "reason": "Judge explicitly opt-in"},
    }
    judge_cases = []
    answer_results = {}
    for variant in strategies or ["dense", "bm25", "hybrid", "rerank"]:
        cases = []
        for case in golden["cases"]:
            started = time.perf_counter()
            try:
                result = pipeline.retrieve(
                    pipeline.contextual_query(case["question"], case.get("history")),
                    chunks,
                    "benchmark",
                    strategy="hybrid" if variant == "rerank" else variant,
                    top_k=k,
                    rerank=variant == "rerank",
                )
                evidence = result["evidence"]
                if variant == "rerank" and result.get("reranker_status") not in (
                    "cross_encoder",
                    "completed",
                    "reranked",
                ):
                    raise RuntimeError(f"Requested reranker did not execute: {result.get('reranker_status')}")
                ids = list(dict.fromkeys(item["document_id"] for item in evidence))
                forbidden = forbidden_hits(ids, case)
                if forbidden:
                    raise AssertionError(f"Unauthorized retrieval: {forbidden}")
                measured = retrieval_metrics(ids, case["relevant"], k)
                cases.append(
                    {
                        "id": case["id"],
                        "category": case["category"],
                        "status": "completed",
                        "retrieved": ids,
                        "metrics": measured,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                if judge and variant == "rerank":
                    generation = pipeline.generate_answer(case["question"], evidence, case.get("history"))
                    answer_results[case["id"]] = answer_checks(
                        case, generation["answer"], generation.get("status")
                    )
                    judge_cases.append(
                        {
                            **case,
                            "actual_output": generation["answer"],
                            "retrieval_context": [item["text"] for item in evidence],
                            "generation_status": generation.get("status"),
                        }
                    )
            except Exception as exc:
                cases.append(
                    {
                        "id": case["id"],
                        "category": case["category"],
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
        successful = [case for case in cases if case["status"] == "completed"]
        latencies = sorted(case["latency_ms"] for case in successful)
        report["variants"].append(
            {
                "strategy": variant,
                "rerank": variant == "rerank",
                "status": "completed" if len(successful) == len(cases) else "failed",
                "metrics": aggregate([case["metrics"] for case in successful]),
                "latency_ms": {
                    "p50": statistics.median(latencies) if latencies else None,
                    "p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
                    if latencies
                    else None,
                },
                "cases": cases,
            }
        )
    # Answer-level checks need a real generated answer; without one they are not_run, never passes.
    report["answer_checks"] = {
        case["id"]: answer_results.get(case["id"]) or answer_checks(case)
        for case in golden["cases"]
        if answer_checks(case)
    }
    if any(v == "fail" for r in report["answer_checks"].values() for v in r.values()):
        report["status"] = "failed"
    if judge:
        from services.evaluation.judge import evaluate_answers

        report["judge"] = evaluate_answers(judge_cases)
    if any(item["status"] != "completed" for item in report["variants"]):
        report["status"] = "failed"
    if judge and report["judge"]["status"] != "completed":
        report["status"] = "failed"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategies", nargs="+", choices=["dense", "bm25", "hybrid", "rerank"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/results/latest.json")
    parser.add_argument("--min-recall", type=float, default=0.6)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("k must be positive")
    report = run_benchmark(args.strategies, args.k, args.judge)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{report['status']}: {args.output}")
    failed = report["status"] != "completed" or any(
        v["metrics"]["recall"] is None or v["metrics"]["recall"] < args.min_recall for v in report["variants"]
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
