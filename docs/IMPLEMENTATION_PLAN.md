# Enterprise RAG implementation plan

The supplied master specification is the approved product direction. Build a modular monorepo; credentials and public deployment validation are deferred until supplied. No paid inference is enabled by default.

## Components and acceptance criteria

1. `apps/api/rag_api`: FastAPI, SQLAlchemy metadata, authentication, tenant/workspace membership, ACLs, durable leased jobs, document lifecycle, conversations, telemetry. Acceptance: uploads enter a durable queue, retry and deletion are safe, unauthorized reads/retrieval fail, API integration tests pass.
2. `services/rag`: parsing, chunking, embeddings, Qdrant/Pinecone adapters, BM25, RRF, reranking and grounded generation. Acceptance: deterministic provider contracts and ranking/security tests pass; real model runs are separately labeled.
3. `apps/web`: Next.js application with chat, library, search inspector, evaluations, administration and settings. Acceptance: TypeScript, tests and production build pass; errors and empty states are honest.
4. `services/evaluation`, `datasets`, `infra`, `.github`: golden corpus, deterministic metrics, DeepEval adapters, reproducible CI and deployment templates. Acceptance: machine-readable measured results and no mandatory paid API.

## Shared backend/RAG contract

`services.rag.pipeline` exposes `parse_document(data: bytes, filename: str) -> list[dict]` with text/page/section; `chunk_pages(pages, strategy='recursive', size=900, overlap=120) -> list[dict]`; `embed_texts(texts: list[str], query=False) -> list[list[float]]`; `index_chunks(namespace: str, chunks: list[dict]) -> None`; `delete_vectors(namespace: str, ids: list[str]) -> None`; `retrieve(query: str, chunks: list[dict], namespace: str, strategy='hybrid', top_k=5, rerank=True) -> dict`; `generate_answer(question: str, evidence: list[dict], history: list[dict] | None=None) -> dict`.

Chunk dictionaries carry id, document_id, title, text, page, section, version and optional embedding. Backend MUST pass only authorized ready/current-version chunks to retrieve. Retrieval returns evidence, candidates, timings, query, strategy. Generation returns answer, citations (subset of supplied evidence), provider, model, usage, status. Exceptions propagate; never substitute mock live output.

## API/UI contract

API prefix `/api/v1`. JSON arrays for list endpoints. Auth: POST `/auth/register` {email,password,name,organization_name}, POST `/auth/login` {email,password}, POST `/auth/demo`; returns {access_token,user:{id,email,name,role,organization_id,workspace_id}}. GET `/auth/me` returns user. Bearer tokens in memory/session storage; no cookie auth. Documents GET/POST multipart(file,access_scope=workspace), GET/DELETE `/{id}`, POST `/{id}/reindex`, GET `/{id}/source`. GET `/ingestion-jobs`; POST `/ingestion-jobs/run` bounded admin worker. GET/POST `/chat/sessions`, GET/DELETE `/chat/sessions/{id}`. POST `/chat` {question,session_id?,strategy?,top_k?,rerank?} returns {answer,citations,session_id,message_id,metrics,status}. POST `/chat/stream` same body with SSE events status/result/error/done. POST `/search` and `/search/debug` {query,strategy,top_k,rerank}; GET `/evaluations`, `/analytics`, `/admin`, `/settings`, `/health`; POST `/feedback` {message_id,rating,comment?}. GET/POST `/collections`. GET `/organizations`, `/workspaces`. API endpoint failures have detail string and proper status.

## Review rationale

Engineering: SQL is the authority for permissions; vector candidates are filtered to allowed document IDs before external inference. A durable SQL job table avoids volatile background tasks. Qdrant local serves CPU development; Pinecone is the hosted dense adapter; BM25 provides independent lexical ranking. RRF needs no incomparable score calibration. LCEL composes prompting with a compatible provider. Local models are lazy-loaded, deterministic tests inject fakes only explicitly.

Operations: free Render disk cannot hold persistent data. Hosted configuration requires PostgreSQL, persistent object storage and Pinecone. Free worker availability and CPU model memory are real constraints: bounded admin ingestion and a prepared small corpus, with honest unavailable responses on exhausted providers. No deployment or semantic quality claim without execution evidence.
