import math

import pytest

from services.evaluation.benchmark import load_dataset
from services.evaluation.metrics import aggregate, answer_checks, retrieval_metrics


def test_known_ranking_and_duplicates():
    score = retrieval_metrics(["wrong", "a", "a", "b"], ["a", "b"], 4)
    assert score["recall"] == 1
    assert score["precision"] == 0.5
    assert score["mrr"] == 0.5
    assert score["ndcg"] == pytest.approx((1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3)))


def test_missing_relevance_is_not_a_perfect_score():
    assert retrieval_metrics([], [], 3)["recall"] is None
    assert retrieval_metrics([], ["a"], 3)["recall"] == 0
    assert aggregate([])["recall"] is None
    with pytest.raises(ValueError):
        retrieval_metrics([], [], 0)


def test_dataset_integrity():
    corpus, golden = load_dataset()
    ids = {doc["id"] for doc in corpus["documents"]}
    assert len(ids) == len(corpus["documents"])
    assert len(golden["categories"]) == 12
    assert set(golden["categories"]) == {case["category"] for case in golden["cases"]}
    assert all(set(case["relevant"]) <= ids for case in golden["cases"])
    assert corpus["fictional"] is True


def test_deepeval_deterministic_gate_detects_regression():
    from deepeval.test_case import LLMTestCase

    from services.evaluation.deepeval_metrics import RetrievalRecallMetric

    metric = RetrievalRecallMetric(["a", "b"], threshold=1)
    assert (
        metric.measure(LLMTestCase(input="question", actual_output="answer", retrieval_context=["a", "b"]))
        == 1
    )
    assert metric.is_successful()
    metric.measure(LLMTestCase(input="question", actual_output="answer", retrieval_context=["wrong"]))
    assert not metric.is_successful()


def test_missing_judge_is_not_run(monkeypatch):
    from services.evaluation.judge import evaluate_answers

    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    assert evaluate_answers([])["status"] == "not_run"


def _answer_case(**extra):
    return {"id": "x", "category": "c", "question": "q", "relevant": [], **extra}


def test_abstention_check_passes_and_fails():
    case = _answer_case(expect_abstention=True)
    assert answer_checks(case, "no evidence", "abstained") == {"abstention": "pass"}
    assert answer_checks(case, "The deductible is $500.", "answered") == {"abstention": "fail"}
    assert answer_checks(case) == {"abstention": "not_run"}


def test_forbidden_answer_check_passes_and_fails():
    case = _answer_case(forbidden_answer="19 million")
    assert answer_checks(case, "The connector supports CSV.", "answered") == {"forbidden_answer": "pass"}
    assert answer_checks(case, "Budget is 19 Million.", "answered") == {"forbidden_answer": "fail"}
    assert answer_checks(case) == {"forbidden_answer": "not_run"}
    assert answer_checks(_answer_case()) == {}


def test_golden_answer_fields_are_covered_by_checks():
    _, golden = load_dataset()
    assert any(answer_checks(case) for case in golden["cases"])


def test_forbidden_retrieval_check_can_fail():
    from services.evaluation.benchmark import build_chunks, forbidden_hits, visible_to_member
    from services.rag.retrieval import lexical_search

    corpus, golden = load_dataset()
    case = next(c for c in golden["cases"] if c["id"] == "q10")
    everything = build_chunks(corpus)
    assert {"private", "expenses_old"} <= {c["id"] for c in everything}
    visible = [c for c in everything if visible_to_member(c)]
    assert not {"private", "expenses_old"} & {c["id"] for c in visible}

    def top_ids(chunks):
        return [chunks_by_id[i]["document_id"] for i, _ in lexical_search(case["question"], chunks, 5)]

    chunks_by_id = {c["id"]: c for c in everything}
    # Without the visibility filter the private memo is retrieved and the check fires; with it, it does not.
    assert forbidden_hits(top_ids(everything), case) == ["private"]
    assert forbidden_hits(top_ids(visible), case) == []
