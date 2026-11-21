"""Versioned, operator-supplied cost estimates; never infer invoices from tokens."""

import json
import os
from decimal import Decimal
from pathlib import Path


def estimate_cost(provider: str, model: str, usage: dict) -> dict:
    result: dict = {
        "actual_billed_cost": None,
        "estimated_paid_equivalent_cost": None,
        "pricing_version": None,
        "currency": "USD",
    }
    if provider == "ollama":
        return {
            **result,
            "estimated_paid_equivalent_cost": 0.0,
            "pricing_version": "local-no-api-1",
            "cost_note": "No inference API charge; electricity and hardware excluded",
        }
    path = os.getenv("PRICING_REGISTRY_PATH")
    if not path or usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        return result
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    rate = registry.get("models", {}).get(f"{provider}/{model}")
    if not rate:
        return result
    input_rate = Decimal(str(rate["input_per_million_usd"]))
    output_rate = Decimal(str(rate["output_per_million_usd"]))
    if not input_rate.is_finite() or not output_rate.is_finite() or min(input_rate, output_rate) < 0:
        raise ValueError("Pricing rates must be finite and nonnegative")
    estimate = (
        Decimal(usage["input_tokens"]) * input_rate + Decimal(usage["output_tokens"]) * output_rate
    ) / 1_000_000
    return {
        **result,
        "estimated_paid_equivalent_cost": float(estimate),
        "pricing_version": registry["version"],
    }
