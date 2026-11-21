# Troubleshooting

| Symptom | Check and recovery |
|---|---|
| Model download cannot resolve host | Check proxy/DNS/network access. Retry model installation; do not replace semantic output with test embeddings. |
| Ollama unavailable | Start Ollama, verify `http://localhost:11434/api/tags`, pull the configured model, check `LLM_BASE_URL`. |
| DeepEval judge not_run | Set `EVAL_JUDGE_MODEL` and use `--judge`; an absent judge is not a pass. |
| Dense query has no indexed data | Run ingestion to ready status and verify namespace, vector backend, model and dimension. |
| Reranker unavailable | Verify model download/cache and `RERANKER_PROVIDER`; inspect `reranker_status`. A disabled reranker is not an executed experiment. |
| Hosted startup rejects configuration | Supply PostgreSQL, Supabase private storage, Pinecone and a strong JWT secret. Ephemeral local storage is deliberately rejected. |
| Free host cold start | Allow startup time; inspect Render resource logs. Do not report cold requests as warm latency. |
| Supabase project paused | Resume it in the provider console and retry health checks. |
| Upload remains queued | Invoke the bounded admin worker or `python -m rag_api.worker --once`. Inspect lease expiry and recorded failure before retry. |
| Qdrant lock error | Stop duplicate API/benchmark processes sharing the same local path; use a separate path or `:memory:` for benchmark isolation. |
| Frontend network/CORS error | Match the frontend origin exactly, verify public API URL, and rebuild after changing Next.js public variables. |
| Provider 429 | Respect quota/rate limits and retry later. No paid fallback is enabled automatically. |
| Scanned PDF empty | Supply a text PDF or run OCR externally; this installation does not claim built-in OCR. |
