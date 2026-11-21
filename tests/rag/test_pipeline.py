import io
import zipfile

import pytest

from services.rag.embeddings import embed_texts
from services.rag.generation import ABSTENTION, generate_answer, validate_answer
from services.rag.parsing import DocumentError, chunk_pages, parse_document
from services.rag.retrieval import contextual_query, lexical_search, reciprocal_rank_fusion, retrieve
from services.rag.vectors import delete_vectors, index_chunks


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for key, value in {
        "APP_ENV": "test",
        "EMBEDDING_PROVIDER": "test_hash",
        "EMBEDDING_DIMENSION": "384",
        "QDRANT_PATH": ":memory:",
        "VECTOR_BACKEND": "qdrant",
        "RERANKER_PROVIDER": "none",
    }.items():
        monkeypatch.setenv(key, value)


def chunk(identifier, text, document="policy"):
    return {
        "id": identifier,
        "document_id": document,
        "text": text,
        "title": document,
        "page": 1,
        "version": 1,
    }


def test_markdown_provenance_and_chunking():
    pages = parse_document(b"# Leave\nApproval by manager.\n# Probation\nNo annual leave.", "policy.md")
    assert [p["section"] for p in pages] == ["Leave", "Probation"]
    result = chunk_pages(pages)
    assert result[1]["parent_index"] == 1
    assert result[1]["section"] == "Probation"
    assert result[1]["start_offset"] == 0


@pytest.mark.parametrize(
    "data,name",
    [(b"MZbad", "safe.txt"), (b"not pdf", "x.pdf"), (b"", "x.txt"), (b"abc", "x.exe"), (b"\xff", "x.txt")],
)
def test_invalid_files(data, name):
    with pytest.raises(DocumentError):
        parse_document(data, name)


def test_html_scripts_never_become_evidence():
    result = parse_document(b"<h1>Policy</h1><script>secret()</script><p>Use MFA</p>", "a.html")
    assert "secret" not in result[0]["text"]
    assert "MFA" in result[0]["text"]


def test_csv_preserves_header_value_relationships():
    result = parse_document(b"role,days\nemployee,20\ncontractor,0", "a.csv")
    assert "role: contractor; days: 0" in result[0]["text"]


def test_macro_docx_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/vbaProject.bin", "bad")
    with pytest.raises(DocumentError, match="Macro"):
        parse_document(buffer.getvalue(), "bad.docx")


def test_scanned_pdf_is_not_silently_indexed():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(DocumentError, match="OCR"):
        parse_document(buffer.getvalue(), "scan.pdf")


def test_bm25_exact_identifier():
    chunks = [
        chunk("a", "Error AUTH-401 requires rotating credentials"),
        chunk("b", "Employees take annual leave"),
    ]
    assert lexical_search("AUTH-401", chunks, 2)[0][0] == "a"
    assert lexical_search("unicorn", chunks, 2) == []


def test_rrf_combines_ranks_and_deduplicates():
    result = reciprocal_rank_fusion([[("a", 0.1), ("b", 0.9)], [("b", 100), ("c", 1)]])
    assert result[0][0] == "b"
    assert len(result) == 3


def test_real_local_vector_acl_namespace_and_deletion():
    allowed = chunk("allowed", "annual leave approval manager")
    private = chunk("private", "secret annual leave approval salary")
    other = chunk("other", "annual leave approval manager")
    index_chunks("tenant-a", [allowed, private])
    index_chunks("tenant-b", [other])
    result = retrieve("annual leave", [allowed], "tenant-a", rerank=False)
    assert [c["id"] for c in result["evidence"]] == ["allowed"]
    result = retrieve("annual leave", [other], "tenant-a", strategy="dense", rerank=False)
    assert result["evidence"] == []
    delete_vectors("tenant-a", ["allowed"])
    assert retrieve("annual leave", [allowed], "tenant-a", strategy="dense", rerank=False)["evidence"] == []


def test_test_embeddings_fail_closed_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="restricted"):
        embed_texts(["test"])


def test_citations_require_authorized_ids_and_actual_references():
    evidence = [chunk("c1", "Manager approval is required.")]
    _answer, citations, status = validate_answer(
        {"answer": "Manager approval is required. [c1]", "citation_ids": ["c1"], "abstained": False}, evidence
    )
    assert status == "answered" and citations[0]["document_id"] == "policy"
    for payload in [
        {"answer": "Secret [private]", "citation_ids": ["private"], "abstained": False},
        {"answer": "Uncited claim", "citation_ids": ["c1"], "abstained": False},
        {"answer": "Claim [c1]\n\nAnother unsupported paragraph", "citation_ids": ["c1"], "abstained": False},
    ]:
        with pytest.raises(ValueError):
            validate_answer(payload, evidence)


def test_empty_context_abstains_without_calling_provider():
    result = generate_answer("What is my salary?", [])
    assert result["answer"] == ABSTENTION and result["provider"] is None


def test_followup_and_topic_switch():
    history = [{"role": "user", "content": "What is the leave policy?"}]
    assert "leave policy" in contextual_query("What about contractors?", history)
    assert contextual_query("How do API keys work?", history) == "How do API keys work?"


@pytest.mark.parametrize(
    "question", ["And who approves it?", "And when does it start?", "They get how many days?"]
)
def test_short_followups_resolve_against_history(question):
    history = [{"role": "user", "content": "What is the leave policy?"}]
    assert "leave policy" in contextual_query(question, history)


def test_long_standalone_questions_are_not_treated_as_followups():
    history = [{"role": "user", "content": "What is the leave policy?"}]
    for q in [
        "And how do employees configure single sign-on for every regional office we operate?",
        "This quarter we want to understand how expense approvals work for contractors abroad",
    ]:
        assert contextual_query(q, history) == q


def test_docx_merges_paragraphs_and_keeps_heading_boundaries():
    from docx import Document

    doc = Document()
    doc.add_heading("Leave", 1)
    doc.add_paragraph("Employees get 20 days.")
    doc.add_paragraph("Approval by manager.")
    doc.add_heading("Probation", 1)
    doc.add_paragraph("No annual leave.")
    buffer = io.BytesIO()
    doc.save(buffer)
    pages = parse_document(buffer.getvalue(), "p.docx")
    assert [p["section"] for p in pages] == ["Leave", "Probation"]
    assert "20 days.\nApproval by manager." in pages[0]["text"]
    small = parse_document(buffer.getvalue(), "p.docx", unit_size=30)
    assert len(small) > 2 and all(p["section"] in {"Leave", "Probation"} for p in small)


def test_structure_chunking_splits_at_headings_unlike_recursive():
    pages = [{"text": "# A\nalpha text\n# B\nbeta text", "page": None, "section": ""}]
    assert len(chunk_pages(pages, "recursive")) == 1
    structured = chunk_pages(pages, "structure")
    assert [c["section"] for c in structured] == ["A", "B"]
    assert structured[1]["start_offset"] == pages[0]["text"].index("# B")


def test_list_items_each_need_a_citation():
    evidence = [chunk("c1", "x"), chunk("c2", "y")]
    ok = {"answer": "Rules:\n- First [c1]\n- Second [c2]", "citation_ids": ["c1", "c2"], "abstained": False}
    assert validate_answer(ok, evidence)[2] == "answered"
    bad = {"answer": "Rules:\n- First [c1]\n2. Second uncited", "citation_ids": ["c1"], "abstained": False}
    with pytest.raises(ValueError, match="paragraph"):
        validate_answer(bad, evidence)


def test_non_citation_brackets_and_id_formatting():
    uid = "123e4567-e89b-12d3-a456-426614174000"
    evidence = [chunk(uid, "x")]
    answer = f"Export as [CSV] per [the guide](http://x.io). [ {uid.upper()} ]"
    _answer, citations, _ = validate_answer(
        {"answer": answer, "citation_ids": [uid.upper()], "abstained": False}, evidence
    )
    assert citations[0]["citation_id"] == uid and f"[{uid}]" in _answer
    other = "123e4567-e89b-12d3-a456-426614174999"
    with pytest.raises(ValueError):
        validate_answer(
            {"answer": f"Claim [{uid}] [{other}]", "citation_ids": [uid], "abstained": False}, evidence
        )


def test_token_budget_limits_context(monkeypatch):
    monkeypatch.setenv("CONTEXT_TOKEN_BUDGET", "100")
    chunks = [chunk(f"c{i}", f"annual leave approval manager word{i} " * 5) for i in range(5)]
    result = retrieve("annual leave", chunks, "tenant-t", strategy="bm25", rerank=False)
    assert 0 < len(result["evidence"]) < 5 and result["context_tokens"] <= 100


def test_reranker_fallback_reason_is_reported(monkeypatch):
    from services.rag import retrieval

    monkeypatch.setenv("RERANKER_PROVIDER", "fastembed")
    monkeypatch.setattr(
        retrieval, "_cross_encoder", lambda *a: (_ for _ in ()).throw(RuntimeError("no model"))
    )
    result = retrieve("annual leave", [chunk("a", "annual leave approval")], "tenant-r", strategy="bm25")
    assert result["reranker_status"] == "unavailable_fallback" and result["reranker_fallback"] is True
    assert "no model" in result["reranker_reason"]
    assert (
        retrieve("annual leave", [chunk("a", "annual leave")], "t", strategy="bm25", rerank=False)[
            "reranker_reason"
        ]
        is None
    )


@pytest.mark.parametrize("strategy", ["dense", "bm25", "hybrid"])
def test_text_is_fetched_only_for_the_candidate_pool(monkeypatch, strategy):
    monkeypatch.setenv("RETRIEVAL_CANDIDATES", "20")
    corpus = [
        chunk(f"c{i:04d}", f"filler topic {i} " + ("annual leave approval " if i % 50 == 0 else ""))
        for i in range(1000)
    ]
    index_chunks("tenant-big", corpus)
    by_id = {c["id"]: c for c in corpus}
    fetched, scanned = [], []

    def fetch(ids):
        fetched.extend(ids)
        return [by_id[i] for i in ids]

    def scan():
        for c in corpus:
            scanned.append(c["id"])
            yield c["id"], c["text"]

    ids_only = [{"id": c["id"]} for c in corpus]
    result = retrieve(
        "annual leave approval",
        ids_only,
        "tenant-big",
        strategy=strategy,
        top_k=5,
        rerank=False,
        fetch=fetch,
        scan=scan,
    )
    assert result["evidence"] and all("text" in c for c in result["evidence"])
    assert len(fetched) <= 5 + 20  # top_k + candidate pool, not 1000
    # Only BM25 needs the streamed scan; dense/hybrid-dense never read the corpus text for candidates.
    assert bool(scanned) == (strategy != "dense")
    if strategy == "bm25":
        assert {c["id"] for c in result["evidence"]} <= {f"c{i:04d}" for i in range(0, 1000, 50)}
