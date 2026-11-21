# Portfolio material

Use only claims supported by the code and your recorded verification. Add a live URL only after deployment succeeds. Add measured numbers from the JSON artifacts with dataset/model details; no performance uplift is asserted here.

## Resume bullets

- Built a modular FastAPI and Next.js knowledge assistant with SQL-backed document permissions, durable ingestion jobs and evidence-linked answers.
- Implemented dense and BM25 retrieval with reciprocal-rank fusion, CPU cross-encoder reranking, and Qdrant/Pinecone adapters.
- Integrated deterministic retrieval regression gates with a versioned fictional dataset (12 docs, 24 questions) and an optional local DeepEval judge adapter (no judge run has been recorded yet; generation-level checks are `not_run`).

Repository description: Permission-aware enterprise RAG assistant with hybrid retrieval, source citations, local inference, DeepEval evaluation and cloud deployment templates.

## Case study

The problem is finding policy and engineering answers without exposing another workspace's documents or treating model prose as verified evidence. The design keeps SQL authorization authoritative, indexes versioned chunks, fuses lexical and semantic rankings, optionally reranks candidates, and constrains citations to supplied evidence. A fictional corpus makes the demonstration shareable. Metrics separate retrieval quality from generation quality; missing judges and provider failures stay visible.

The difficult tradeoffs are CPU latency versus model size, local persistence versus ephemeral free hosting, corpus-wide BM25 simplicity versus scalable sparse indexing, and deterministic CI versus expensive judge evaluations. RRF avoids calibrating unrelated score scales. Free hosting is a deployment constraint rather than an enterprise availability claim.

## Walkthrough to record

1. Show the configured demo workspace and safe documents.
2. Ask about probation leave and open a source citation.
3. Search `AUTH-401-TOKEN-EXPIRED` and compare retrieval strategies.
4. Ask about the conflicting travel policy versions (demo only: conflict handling has no measured answer-level result).
5. Ask an unsupported dental question and show the actual abstention behavior (demo only: abstention is unmeasured; the `expect_abstention` check is `not_run` without a generator).
6. Demonstrate permission denial for the restricted memo (retrieval-level exclusion is checked by the `forbidden` metric; answer behavior is unmeasured).
7. Open an actual evaluation report, explain dataset size and limitations.
8. Show ingestion failures and provider-unavailable states honestly.

## Interview prompts

Why authorize before retrieval? Why RRF instead of adding scores? How do document versions prevent stale evidence? What happens after vector upsert succeeds but SQL fails? How do leases recover crashed jobs? How can a local judge be wrong? What changes when moving from one process to many replicas? What does a perfect score on 24 questions fail to establish?
