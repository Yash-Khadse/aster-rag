# Delivery status

## Implemented and exercised

- FastAPI/Next.js monorepo with persistent authentication, role-based membership, isolated workspaces, collections, groups and document ACL endpoints.
- Six initial document formats, validated uploads, checksums, durable leased ingestion/retry/delete jobs, versioned chunk manifests and authorized source downloads.
- Local BGE embeddings, real Qdrant dense search, independent BM25, RRF, bounded ONNX cross-encoder reranking, context budgets and follow-up resolution.
- LCEL generation adapters for Ollama, Groq, Gemini and explicitly opt-in OpenAI; citation-ID and paragraph-reference validation, abstention for empty evidence, persisted conversations and feedback.
- Chat, document library, four-way search inspector, measured evaluation table, admin inspection and settings UI. SSE progress plus validated final result.
- Versioned fictional corpus and golden questions, deterministic DeepEval gate, optional local judge, measured CPU retrieval report, CI checks, deployment templates and setup guides.

## Requires environment values or installed models

- Live generative answers and judge metrics need Ollama with a pulled model, or a configured compatible provider. The tests use clearly scoped doubles for generation, not fabricated live answers.
- Pinecone and Supabase adapters require credentials and live integration testing. Hosted free-instance memory/cold-start viability is not yet established.
- Public hosting requires account resources, repository remote and deployment verification. No deployed URL is claimed.

## Limitations, not completed production features

- Scanned PDFs can use the opt-in CPU OCR adapter when Poppler and Tesseract are installed. Those binaries are not bundled and real OCR quality is unverified. With OCR disabled/missing, extraction fails explicitly. XLSX/PPTX are outside initial formats.
- Chunking offers fixed, recursive and page/section-preserving structure strategies; semantic chunking and parent expansion are not benchmarked or enabled.
- Citation validation establishes identity and formatting, not semantic entailment of every claim. Real generation faithfulness remains unevaluated.
- SSE does not stream raw model tokens; time-to-first-token is not measured.
- BM25 scans the authorized corpus at query time and is designed for a bounded portfolio corpus. Embedded Qdrant has one-process ownership.
- In-process authentication throttling is not a distributed edge limiter. Production MFA, password recovery, token revocation, antivirus/parser isolation, automated retention and distributed cleanup reconciliation remain hardening work.
- Database/source/vector operations are retryable but are not one atomic distributed transaction. Interrupted external writes require operational reconciliation before production use.
- The tiny synthetic benchmark does not prove general accuracy or compliance. No production SLA or certification is claimed.

## Known limits and what is unmeasured

- Benchmark: 12 fictional documents, 24 questions, unchunked (`limits.chunked: false` in reports). Differences between strategies on 20 labeled questions are not statistically meaningful.
- The full retrieval benchmark (dense, BM25, hybrid, rerank) was rerun on the corrected harness on 2026-11-21 (`datasets/results/local-onnx.json`, CPU; the earlier run is kept as `local-onnx.pre-harness-fix.json`). Quality metrics were unchanged; latencies are single-run, uncontrolled-load figures.
- No judge or generation run has been recorded: faithfulness, answer relevancy, abstention (`expect_abstention`) and prompt-injection (`forbidden_answer`) checks are `not_run`.
- Conflict handling (archived vs current policy) and the dental-question abstention demo have no measured backing.
- Permission checks in the benchmark cover a single plain-member view; role, group and restricted-scope cases are covered by API tests, not by the benchmark corpus.

## How to run the real-model faithfulness + abstention + injection evaluation

**Status: this has NOT been run on this machine.** Ollama is not installed here and no hosted LLM keys are configured, so every faithfulness, answer-relevancy, contextual-precision/recall, abstention (`expect_abstention`) and prompt-injection (`forbidden_answer`) result is `not_run`. Nothing below has been executed; treat the commands as unverified until you run them.

1. Install Ollama from the official installer (https://ollama.com/download) and start it (`ollama serve`, or the desktop app). It listens on `http://localhost:11434`.
2. Pull the model: `ollama pull qwen2.5:3b`. The same model serves as answer generator (`LLM_PROVIDER=ollama`, the default) and as judge.
3. From the repository root in PowerShell (do not run `uv sync`; `--extra` is enough):

```powershell
$env:LLM_PROVIDER='ollama'
$env:LLM_MODEL='qwen2.5:3b'
$env:EVAL_JUDGE_MODEL='qwen2.5:3b'
uv run --extra evaluation python -m services.evaluation.benchmark --strategies rerank --judge --output datasets/results/judge-qwen2.5-3b.json
```

4. Results land in `datasets/results/judge-qwen2.5-3b.json` (the default without `--output` is `datasets/results/latest.json`). Look at: `answer_checks` (per case, `pass` / `fail` / `not_run`), `judge.status` and `judge.cases[].metrics[]` (`name`, `score`, `passed`, `reason`). Answers are generated and judged only for the `rerank` variant. Expect a CPU run to take many minutes.
5. Pass criteria: an `abstention` check passes only if the generator status is `abstained` for an unanswerable question; a `forbidden_answer` check passes only if the forbidden string (for example an injected instruction's payload) is absent from the answer. Judge metrics (DeepEval Faithfulness, AnswerRelevancy, and for labeled questions ContextualPrecision/ContextualRecall) each pass when their score meets DeepEval's default threshold; the judge `status` is `completed` only if every metric of every case passed, otherwise `failed`. Any `fail`, failed judge call or failed variant sets the report `status` to `failed` and the CLI exits nonzero. `not_run` means no real evidence either way. A 3B local judge is stochastic and can mis-score, so read each `reason` before quoting a result and report the model name alongside the numbers.
