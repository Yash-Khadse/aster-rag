# Reranking experiments

The benchmark compares dense, BM25, hybrid and hybrid plus cross-encoder with the same golden questions and top-k. A requested reranker that did not execute causes a failed benchmark variant. A fallback is not a measured cross-encoder result.

Run `uv run --extra evaluation python -m services.evaluation.benchmark --output datasets/results/reranking.json`. The default FastEmbed ONNX cross-encoder does not require PyTorch. Record model identities, dataset hash, per-case ranking, p50/p95 wall time and cold/warm conditions. The first model load contributes to cold latency; compare warmed runs separately before making performance claims.

No result is asserted until the command runs successfully. Do not infer that reranking improves quality merely because the architecture includes it. Expand the dataset with difficult near-duplicate policies and independently labeled relevance before making general claims.

## Recorded CPU run

`datasets/results/local-onnx.json` contains the executed BGE-small / ONNX MiniLM comparison on dataset `aster-1.0`, run on 2026-11-21 on the corrected harness (CPU only, Intel64 Family 6 Model 186, no GPU; other processes were running, so latencies are indicative only). Artifact `limits`: `n_docs` 12, `n_visible_docs` 10, `n_questions` 24, `chunked` false. All 12 documents are indexed and the member visibility filter is applied at retrieval; forbidden (archived/private) documents were retrieved 0 times (any hit would fail the case; all 24 cases completed for every variant). No language-model judge ran (`judge.status: not_run`). Retrieval metrics exclude questions without positive relevance labels; they do not measure abstention quality.

| Method | Recall@5 | Precision@5 | MRR | nDCG@5 | Forbidden hits | p50 retrieval | p95 retrieval |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense | 1.00 | 0.22 | 1.00 | 1.000 | 0 | 38.3 ms | 65.6 ms |
| BM25 | 0.95 | 0.21 | 0.925 | 0.932 | 0 | 0.8 ms | 1.3 ms |
| Hybrid | 1.00 | 0.22 | 0.96 | 0.969 | 0 | 52.7 ms | 70.0 ms |
| Hybrid + reranker | 1.00 | 0.22 | 1.00 | 1.000 | 0 | 765.1 ms | 2179.4 ms |

Toy corpus, single run: this small corpus does not demonstrate a hybrid advantage over dense search. On 20 labeled questions (24 minus 4 without relevance labels) the reranker's MRR (1.00) was higher than hybrid's (0.96) at about 15x the p50 latency; one run on 20 questions cannot establish a reliable quality difference. These are retrieval-only timings (models already downloaded, process-local initialization included), not end-to-end answer latency or a production SLA.

Versus the earlier table (`datasets/results/archive/local-onnx.pre-harness-fix.json`, run 2026-10-29 on the old harness that hid private/archived documents before indexing): the quality metrics are identical (recall, precision, MRR and nDCG unchanged for all four methods), so the harness fix did not change retrieval quality on this corpus. Latencies were higher in this run (p50: dense 24.6 to 38.3 ms, BM25 0.5 to 0.8 ms, hybrid 25.5 to 52.7 ms, reranker 475.0 to 765.1 ms; p95: dense 35.6 to 65.6 ms, hybrid 32.9 to 70.0 ms, reranker 1476.3 to 2179.4 ms). Two more documents are indexed now, and machine load may also differ; the runs were not controlled for load, so do not read the latency change as a regression or improvement.
