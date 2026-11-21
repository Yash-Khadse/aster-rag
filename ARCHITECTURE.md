# Architecture

SQL metadata is the authority for ownership, document status and versions. Vector storage accelerates similarity search; it never grants permission. The backend selects authorized current chunks before retrieval or model inference. BM25 operates on that same authorized set.

```mermaid
flowchart LR
  Browser[Next.js browser] --> API[FastAPI bearer auth]
  API --> SQL[(SQLite local / PostgreSQL hosted)]
  API --> Objects[(Local files / Supabase Storage)]
  SQL --> Jobs[Durable leased ingestion jobs]
  Jobs --> Parse[Parse and chunk]
  Parse --> Embed[CPU embeddings]
  Embed --> Vectors[(Qdrant / Pinecone)]
  API --> Retrieval[Authorized hybrid retrieval]
  Vectors --> Retrieval
  Retrieval --> Rank[Optional cross-encoder]
  Rank --> LLM[Ollama / compatible provider]
  LLM --> API
```

```mermaid
sequenceDiagram
  participant U as User
  participant A as API
  participant S as SQL
  participant R as Retrieval
  participant L as LLM
  U->>A: Bearer token + question
  A->>S: Membership, workspace, document ACL and ready version
  S-->>A: Authorized chunk set
  A->>R: Query + authorized chunks
  R-->>A: Ranked evidence
  A->>L: Untrusted evidence + bounded history
  L-->>A: Grounded answer
  A->>A: Validate citations against evidence
  A-->>U: Answer, citations, telemetry
```

Keep one API process for local embedded Qdrant. SQL jobs survive API restarts; the bounded worker can be invoked again after its lease expires. Free hosting has no persistent worker guarantee. See INGESTION_PIPELINE.md.
