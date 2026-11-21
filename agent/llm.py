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
# Transcription (media.py, off by default): USD per 1M audio-input / text-output tokens, and per minute when the
# response carries no token usage (whisper-1). OpenAI list prices; confirm with the gateway's model list first.
TRANSCRIBE_PRICES = {
    "gpt-4o-mini-transcribe": (3.00, 5.00, 0.003),
    "gpt-4o-transcribe": (6.00, 10.00, 0.006),
    "whisper-1": (0.0, 0.0, 0.006),
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


def transcribe(filename: str, data: bytes, model: str, prompt: str, timeout: float) -> tuple[str, float]:
    """One transcription through the gateway (media.py). Returns (text, cost in USD). No retry."""
    if model not in TRANSCRIBE_PRICES:
        raise KeyError(f"No price for {model}: add it to llm.TRANSCRIBE_PRICES so its cost gets logged")
    resp = client().with_options(timeout=timeout, max_retries=0).audio.transcriptions.create(
        model=model, file=(filename, data), prompt=prompt)
    price_in, price_out, per_minute = TRANSCRIBE_PRICES[model]
    usage = getattr(resp, "usage", None)
    tokens_in, tokens_out = getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
    if tokens_in is not None:
        cost = ((tokens_in or 0) * price_in + (tokens_out or 0) * price_out) / 1_000_000
    else:  # billed per minute: the duration if the response says it, else ~1 MB per minute of a phone memo
        seconds = getattr(usage, "seconds", None) or getattr(resp, "duration", None) or len(data) / 1_000_000 * 60
        cost = float(seconds) / 60 * per_minute
    print(f"llm transcribe {model} {filename} {len(data)} bytes cost=${cost:.6f}")
    return resp.text or "", cost
