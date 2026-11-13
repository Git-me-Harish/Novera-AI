"""Token cost estimation from configured prices.

Prices change often and differ per provider, so none are built in. Configure
LLM_PRICING as JSON keyed by "provider:model", in USD per million tokens:

    {"openai:gpt-4.1-mini": {"input": 0.40, "output": 1.60, "cached_input": 0.10}}

Unknown models return None, so reports show "unknown" instead of a made-up
number.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from loguru import logger

from app.core.config import settings


@lru_cache(maxsize=1)
def _price_table(raw: str) -> dict[str, dict[str, float]]:
    try:
        table = json.loads(raw or "{}")
    except json.JSONDecodeError:
        logger.error("LLM_PRICING is not valid JSON; cost estimates disabled")
        return {}
    return table if isinstance(table, dict) else {}


def estimate_cost(model_label: Optional[str], usage: dict) -> Optional[float]:
    """USD cost for one call, or None when the model has no configured price."""
    if not model_label:
        return None
    price = _price_table(settings.llm_pricing).get(model_label)
    if not price:
        return None
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    completion = int(usage.get("completion_tokens", 0) or 0)
    cached = min(int(usage.get("cached_tokens", 0) or 0), prompt)
    input_price = float(price.get("input", 0.0))
    cached_price = float(price.get("cached_input", input_price))
    return (
        (prompt - cached) * input_price
        + cached * cached_price
        + completion * float(price.get("output", 0.0))
    ) / 1_000_000
