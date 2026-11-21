"""The only place that calls the LLM gateway (5U's OpenAI proxy).

Every call is priced and logged: LLM cost is 40% of the score, so the budget is one tiny call per RFQ.
"""

import json
import os

from openai import OpenAI

MODEL = os.environ.get("LLM_MODEL", "gpt-4.1-nano")

# USD per 1M tokens (input, output), OpenAI list prices. Check them against the gateway's cost counter.
PRICES = {
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY and OPENAI_BASE_URL (the 5U gateway) from the env
    return _client


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def chat_json(name: str, system: str, user: str, schema: dict, model: str = MODEL) -> tuple[dict, float]:
    """One structured call through the gateway. Returns (parsed JSON, cost in USD).

    `schema` must be a strict JSON schema: every property required, additionalProperties false.
    """
    if model not in PRICES:
        raise KeyError(f"No price for {model}: add it to llm.PRICES so its cost gets logged")
    resp = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
    )
    usage = resp.usage
    cost = cost_usd(model, usage.prompt_tokens, usage.completion_tokens)
    print(f"llm {name}: model={model} in={usage.prompt_tokens} out={usage.completion_tokens} cost=${cost:.6f}")
    message = resp.choices[0].message
    if message.refusal:
        raise RuntimeError(f"LLM refused {name}: {message.refusal}")
    return json.loads(message.content), cost
