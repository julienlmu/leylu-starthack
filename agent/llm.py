"""The only place that calls the LLM gateway (5U's OpenAI proxy).

Every call is priced and logged: LLM cost is 40% of the score, so the budget is one tiny call per RFQ.
"""

import json
import os

from openai import OpenAI

# gpt-6-luna with reasoning off: cheapest per call of the gateway's models we measured, and it got "150 kg each"
# right where gpt-4o-mini halved the weight (live test Sat 15:10, docs/pushlog/20261121-1511-orhun-llm-model.md).
MODEL = os.environ.get("LLM_MODEL") or "gpt-6-luna"

# USD per 1M tokens (input, output), OpenAI list prices, for models the 5U gateway allows.
# Check them against the gateway's cost counter. (gpt-5 models are reasoning models: their thinking is billed as output.)
PRICES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-6.1-terra": (1.00, 5.00),  # escalation actor: ~10x luna, used only when luna's result fails the checks
}

# Extra request fields per model. gpt-6-luna reasons by default (about 2.5x the output tokens): off for extraction.
OPTIONS = {
    "gpt-6-luna": {"reasoning_effort": "none"},
}

_client = None


def client() -> OpenAI:
    """OpenAI client on the 5U gateway. It authenticates with our team key; the gateway adds our OpenAI key
    (stored once via POST /v1/gateway/openai-key) and counts the cost per team."""
    global _client
    if _client is None:
        key = os.environ["FIVEU_API_KEY"]
        base = os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
        # A normal call takes ~4 s; at worst 2 x 20 s still leaves time inside the 2-minute window.
        _client = OpenAI(base_url=f"{base}/v1/gateway", api_key=key, default_headers={"X-API-Key": key},
                         timeout=20, max_retries=1)
    return _client


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def chat_json(name: str, system: str, user: str | list[dict], schema: dict, model: str = MODEL,
              timeout: float | None = None, max_tokens: int | None = None) -> tuple[dict, float]:
    """One structured call through the gateway. Returns (parsed JSON, cost in USD).

    `schema` must be a strict JSON schema: every property required, additionalProperties false.
    `user` is the text, or a list of content parts (an image or a PDF for scans.py). `timeout`: seconds, no retry.
    `max_tokens`: a cap on the output (and so on its cost).
    """
    if model not in PRICES:
        raise KeyError(f"No price for {model}: add it to llm.PRICES so its cost gets logged")
    api = client().with_options(timeout=timeout, max_retries=0) if timeout else client()
    resp = api.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
        **OPTIONS.get(model, {}),
        **({"max_completion_tokens": max_tokens} if max_tokens else {}),
    )
    usage = resp.usage
    cost = cost_usd(model, usage.prompt_tokens, usage.completion_tokens)
    print(f"llm {name}: model={model} in={usage.prompt_tokens} out={usage.completion_tokens} cost=${cost:.6f}")
    message = resp.choices[0].message
    if message.refusal:
        raise RuntimeError(f"LLM refused {name}: {message.refusal}")
    return json.loads(message.content), cost


if __name__ == "__main__":
    # Which models the gateway allows: pick the cheapest that passes the fixtures, and add its price to PRICES.
    for model in client().models.list():
        print(model.id, "(priced)" if model.id in PRICES else "")
