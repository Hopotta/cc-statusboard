"""Published OpenAI API-equivalent rates for locally observed Codex models.

Codex desktop sessions may be covered by a ChatGPT plan, so this is not an
invoice or a record of an API charge.  It answers the useful counterfactual:
what would the observed token mix cost at the published API text-token rate?
Unknown internal aliases intentionally remain unpriced instead of inheriting
another model's price.

Sources (checked 2026-09-13):
https://developers.openai.com/api/docs/models/gpt-5.6-sol
https://developers.openai.com/api/docs/models/gpt-5.6-terra
https://developers.openai.com/api/docs/models/gpt-5.6-luna
https://developers.openai.com/api/docs/models/gpt-5-codex
"""

from __future__ import annotations

from typing import Dict, Mapping, Sequence

from .native_usage import Price

PRICING_AS_OF = "2026-09-13"
PRICING_SOURCE = "OpenAI published API text-token rates"


def _rates(input_per_million: float, cached_per_million: float,
           output_per_million: float) -> Dict[str, float]:
    input_rate = input_per_million / 1_000_000
    return {
        "input": input_rate,
        "cacheRead": cached_per_million / 1_000_000,
        # OpenAI bills cache writes at 1.25× regular input for these models.
        "cacheCreation": input_rate * 1.25,
        "output": output_per_million / 1_000_000,
    }


# Do not infer a price for `codex-auto-review`: it is an internal alias with
# no stable public API SKU.  The resulting coverage field makes that visible.
CODEX_PRICES: Dict[str, Price] = {
    "gpt-5.6-sol": _rates(4.00, 0.40, 20.00),
    "gpt-5.6-terra": _rates(2.00, 0.20, 12.00),
    "gpt-5.6-luna": _rates(0.20, 0.02, 1.20),
    "gpt-5-codex": _rates(1.25, 0.125, 10.00),
    # Older local rollout files name this pre-0.6 family only as `Codex`.
    # The historical model is not recoverable from those logs; this is kept
    # unpriced rather than pretending it was GPT-5-Codex.
}


def _tokens(model: Mapping[str, object]) -> int:
    value = model.get("totalTokens", 0)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def pricing_coverage(models: Sequence[Mapping[str, object]]) -> float | None:
    """Return the share of observed tokens with an exact published rate."""
    total = sum(_tokens(model) for model in models)
    if not total:
        return None
    priced = sum(
        _tokens(model)
        for model in models
        if model.get("modelName") in CODEX_PRICES
    )
    return round(priced / total, 4)
