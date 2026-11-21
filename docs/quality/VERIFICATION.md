# Verification record

The implementation is a portfolio application with local CPU retrieval. A public deployment and live LLM/judge verification require configured providers; neither is claimed.

## Executed on 2026-10-29

- Python suite covers parsing, real local Qdrant ACL/namespace filtering, Pinecone adapter contract, citation integrity, LCEL generation contract, ingestion retry/deletion, tenant separation, API budgets, concurrent permission revocation and a deterministic DeepEval metric. See the final test output for the current count.
- Final full-suite run before the optional OCR addition: **37 passed**. Focused RAG tests are rerun after OCR changes; real OCR remains unverified.
- Frontend: TypeScript check passed; Vitest 6 tests passed; Next.js 16.4.3 production build passed.
- Python Ruff and backend mypy passed after cleanup.
- Playwright desktop/mobile sign-in smoke passed. A second live browser test passed against the seeded API: demo authentication, ready documents, dense/BM25/hybrid/reranked search and imported evaluation results.
- Installed dependency audit reported no known vulnerabilities; the editable project itself is not a published dependency to audit.
- Real FastEmbed BGE-small embeddings and ONNX MiniLM cross-encoder benchmark: all four retrieval variants executed. Report: `datasets/results/local-onnx.json` (rerun 2026-11-21 on the corrected harness; earlier run kept as `local-onnx.pre-harness-fix.json`). This tiny fictional corpus is not a general accuracy benchmark.

Windows sandbox prevented the Python event loop's local socketpair from initializing; API tests were executed outside that sandbox. This was an execution-environment restriction.

## Not verified

- Live generation and LLM-as-judge quality (Ollama/provider credentials not configured).
- Pinecone/Supabase network integration and hosted resource limits.
- Public cloud deployment, cold starts, production concurrency and SLA.
- Real OCR extraction (optional Poppler/Tesseract binaries are not installed; disabled OCR fails explicitly).

The SSE endpoint emits progress and a fully validated final result. It does not expose unvalidated model tokens. Token-by-token generation and time-to-first-token telemetry are not implemented.
