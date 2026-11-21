"""No model calls: deterministic retrieval gate using DeepEval's metric contract."""

from deepeval.metrics import BaseMetric

from services.evaluation.metrics import retrieval_metrics


class RetrievalRecallMetric(BaseMetric):
    def __init__(self, relevant: list[str], k: int = 5, threshold: float = 0.6):
        if not relevant:
            raise ValueError("Recall gate requires at least one relevant document")
        self.relevant = relevant
        self.k = k
        self.threshold = threshold
        self.score = None
        self.success = None
        self.error = None
        self.async_mode = False
        self.strict_mode = False
        self.verbose_mode = False
        self.evaluation_model = "deterministic"
        self.reason = None

    def measure(self, test_case, *args, **kwargs):
        self.score = retrieval_metrics(test_case.retrieval_context or [], self.relevant, self.k)["recall"]
        self.success = self.score >= self.threshold
        self.reason = f"Recall@{self.k}={self.score:.3f}; required {self.threshold:.3f}"
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case)

    def is_successful(self):
        return self.success is True

    @property
    def __name__(self):
        return "Retrieval Recall"
