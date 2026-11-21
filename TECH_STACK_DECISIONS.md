# Technology decisions and two-part review

| Decision | Engineering review | Operational review and alternative |
|---|---|---|
| FastAPI + SQLAlchemy | Typed HTTP and explicit SQL authorization | SQLite minimizes local setup; PostgreSQL required hosted. Django offers more bundled administration but larger framework surface. |
| Local FastEmbed BGE | Small dense model and consistent vectors | CPU compatible; downloads and cache required. E5 needs model-specific query/document instructions; no comparative quality claim yet. |
| Qdrant local / Pinecone hosted | Common vector contract, namespace isolation | Local embedded storage cannot be shared by arbitrary workers. Pinecone avoids ephemeral hosted disk. FAISS is simpler but needs lifecycle/filter orchestration. |
| BM25 + RRF | Lexical identifiers and semantic recall; rank fusion avoids score calibration | BM25 currently scales with authorized corpus. Weighted fusion needs validation; Pinecone integrated hybrid capabilities are an alternative, not assumed equivalent to this adapter. |
| Cross-encoder reranking | Joint query/chunk scoring | Optional model dependency, CPU latency and memory. Hosted reranking adds quotas and data transfer. Disabled or unavailable status must be visible. |
| LangChain prompt composition | Provider-compatible generation and structured prompts | Direct SDK calls would be smaller; no LangGraph because a graph workflow is unnecessary. |
| Ollama / compatible hosted provider | Same provider interface | Local CPU is slower; Groq/Gemini quotas vary. OpenAI is optional and must be deliberately enabled. |
| Recursive/structure-aware chunks | Provenance and deterministic boundaries | Semantic chunking adds embedding cost; not selected without a corpus benchmark. |
| DeepEval | Actual framework metrics plus deterministic retrieval gate | Local judge explicitly configured; mandatory CI never requires paid inference. |
| Render / Vercel / Supabase | Separates UI, API, SQL and durable objects | Free services have idle suspension, memory and quota constraints. A local Docker stack is the fallback; no production SLA. |

Official references: [DeepEval custom models](https://deepeval.com/guides/guides-using-custom-llms), [Pinecone overview](https://docs.pinecone.io/guides/get-started/overview), [Groq compatibility](https://console.groq.com/docs/openai), [Render free services](https://render.com/docs/free). Verify package versions from the committed lockfiles, not from this prose.
