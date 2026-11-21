from types import SimpleNamespace

import pytest

from services.rag import generation, retrieval, vectors
from services.rag.pricing import estimate_cost


def test_pinecone_filters_before_candidates_are_returned(monkeypatch):
    calls = []

    class Index:
        def query(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                matches=[SimpleNamespace(id="authorized", score=0.8), SimpleNamespace(id="secret", score=1)]
            )

    monkeypatch.setattr(vectors, "_backend", lambda: ("pinecone", Index()))
    result = vectors.dense_search("tenant", [0.1], ["authorized"], 5)
    assert result == [("authorized", 0.8)]
    assert calls[0]["filter"] == {"chunk_id": {"$in": ["authorized"]}}
    assert calls[0]["namespace"].startswith("tenant:")


def test_precomputed_embeddings_do_not_run_encoder_again(monkeypatch):
    calls = []
    monkeypatch.setenv("EMBEDDING_DIMENSION", "2")
    monkeypatch.setattr(vectors, "embed_texts", lambda _: pytest.fail("Encoder called twice"))
    monkeypatch.setattr(
        vectors, "_backend", lambda: ("pinecone", SimpleNamespace(upsert=lambda **kw: calls.append(kw)))
    )
    vectors.index_chunks(
        "tenant", [{"id": "c1", "document_id": "d1", "text": "policy", "embedding": [0.1, 0.2]}]
    )
    assert calls[0]["vectors"][0]["metadata"]["chunk_id"] == "c1"


def test_reranker_preserves_metadata_and_uses_query(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "fastembed")

    class Encoder:
        def rerank(self, query, texts):
            assert query == "approval" and texts == ["a", "b"]
            return [0.2, 0.9]

    monkeypatch.setattr(retrieval, "_cross_encoder", lambda *args: Encoder())
    result, status = retrieval.rerank_candidates(
        "approval", [{"id": "1", "text": "a", "page": 1}, {"id": "2", "text": "b", "page": 9}]
    )
    assert status == "cross_encoder" and result[0]["page"] == 9


def test_paid_provider_requires_explicit_optin(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ALLOW_PAID_PROVIDERS", "false")
    with pytest.raises(ValueError, match="Paid providers"):
        generation._llm()


def test_costs_do_not_fabricate_bills(monkeypatch):
    monkeypatch.delenv("PRICING_REGISTRY_PATH", raising=False)
    assert estimate_cost("groq", "unknown", {"input_tokens": 100})["actual_billed_cost"] is None
    local = estimate_cost("ollama", "local", {})
    assert local["estimated_paid_equivalent_cost"] == 0 and local["actual_billed_cost"] is None


def test_lcel_generation_uses_validated_evidence_and_reported_usage(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    def reply(prompt):
        assert "Manager approval" in prompt.to_string()
        return AIMessage(
            content='{"answer":"Approval is required. [c1]","citation_ids":["c1"],"abstained":false}',
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )

    monkeypatch.setattr(generation, "_llm", lambda: (RunnableLambda(reply), "ollama", "test-double"))
    result = generation.generate_answer(
        "Who approves?", [{"id": "c1", "text": "Manager approval", "document_id": "d1"}]
    )
    assert result["status"] == "answered"
    assert result["usage"]["total_tokens"] == 120
    assert result["citations"][0]["document_id"] == "d1"


def test_ocr_missing_binaries_is_explicit(monkeypatch):
    from services.rag import ocr

    monkeypatch.setenv("OCR_ENABLED", "true")
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="unavailable"):
        ocr.ocr_pdf_page(b"pdf", 1)


def _fake_llm(monkeypatch, replies):
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    calls = []

    def reply(prompt):
        calls.append(prompt.to_string())
        return AIMessage(content=replies[min(len(calls), len(replies)) - 1])

    monkeypatch.setattr(generation, "_llm", lambda: (RunnableLambda(reply), "ollama", "test-double"))
    return calls


GOOD = '{"answer":"Approval is required. [c1]","citation_ids":["c1"],"abstained":false}'
EVIDENCE = [{"id": "c1", "text": "Manager approval", "document_id": "d1"}]


def test_json_embedded_in_prose_is_extracted_without_retry(monkeypatch):
    calls = _fake_llm(monkeypatch, [f"Sure! Here you go:\n```json\n{GOOD}\n```\nHope that helps."])
    assert generation.generate_answer("Who approves?", EVIDENCE)["status"] == "answered"
    assert len(calls) == 1


def test_malformed_json_is_reasked_once_then_fails(monkeypatch):
    calls = _fake_llm(monkeypatch, ["not json at all", GOOD])
    assert generation.generate_answer("Who approves?", EVIDENCE)["status"] == "answered"
    assert len(calls) == 2 and "valid JSON only" in calls[1]
    calls = _fake_llm(monkeypatch, ["nope"])
    with pytest.raises(ValueError):
        generation.generate_answer("Who approves?", EVIDENCE)
    assert len(calls) == 2


def test_json_mode_requested_only_for_supporting_providers(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    llm, _, _ = generation._llm()
    assert llm.model_kwargs["response_format"] == {"type": "json_object"}
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert "response_format" not in generation._llm()[0].model_kwargs
