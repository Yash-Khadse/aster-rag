"""DeepEval metrics with an explicitly configured local Ollama judge."""

import asyncio
import os

import httpx
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase


class OllamaJudge(DeepEvalBaseLLM):
    def __init__(self, model: str, base_url: str):
        self.model_name = model
        self.base_url = base_url.rstrip("/").removesuffix("/v1")
        super().__init__(model_name=model)

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str, schema=None):
        payload = {"model": self.model_name, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
        if schema is not None:
            payload["format"] = schema.model_json_schema()
        response = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=180)
        response.raise_for_status()
        output = response.json()["response"]
        return schema.model_validate_json(output) if schema is not None else output

    async def a_generate(self, prompt: str, schema=None):
        return await asyncio.to_thread(self.generate, prompt, schema)

    def get_model_name(self):
        return f"ollama/{self.model_name}"


def evaluate_answers(cases: list[dict]) -> dict:
    model = os.getenv("EVAL_JUDGE_MODEL")
    if not model:
        return {"status": "not_run", "reason": "EVAL_JUDGE_MODEL is not configured"}
    if not cases:
        return {"status": "not_run", "reason": "No generated answers supplied"}
    judge = OllamaJudge(model, os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    results = []
    for case in cases:
        test_case = LLMTestCase(
            input=case["question"],
            actual_output=case["actual_output"],
            expected_output=case["expected"],
            retrieval_context=case["retrieval_context"],
        )
        metrics = [
            FaithfulnessMetric(model=judge, async_mode=False),
            AnswerRelevancyMetric(model=judge, async_mode=False),
        ]
        if case["relevant"]:
            metrics += [
                ContextualPrecisionMetric(model=judge, async_mode=False),
                ContextualRecallMetric(model=judge, async_mode=False),
            ]
        scores = []
        try:
            for metric in metrics:
                metric.measure(test_case)
                scores.append(
                    {
                        "name": metric.__name__,
                        "score": metric.score,
                        "passed": metric.is_successful(),
                        "reason": metric.reason,
                    }
                )
            results.append({"id": case["id"], "status": "completed", "metrics": scores})
        except Exception as exc:
            results.append({"id": case["id"], "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    passed = all(row["status"] == "completed" and all(m["passed"] for m in row["metrics"]) for row in results)
    return {"status": "completed" if passed else "failed", "model": judge.get_model_name(), "cases": results}
