"""One-time setup and health check for the 5U APIs, after filling in the keys in ../.env.

Run from agent/:  uv run --env-file ../.env python setup_5u.py

1. checks the team key (GET /v1/me)
2. stores our OpenAI key in the gateway if it isn't stored yet (POST /v1/gateway/openai-key)
3. lists the models the gateway allows and checks LLM_MODEL is one of them and has a price in llm.PRICES
4. prints the first raw mailbox items, to confirm the field names inbox.FiveUMailbox._mail() reads
"""

import json
import os
import sys

import httpx

import llm
from inbox import FIVEU_BASE_URL, poll_slot


def main() -> None:
    key = os.environ.get("FIVEU_API_KEY")
    if not key:
        sys.exit("FIVEU_API_KEY is empty: put the team key from the kit card into .env")
    api = httpx.Client(base_url=FIVEU_BASE_URL, headers={"X-API-Key": key}, timeout=30)

    me = api.get("/v1/me")
    if me.status_code != 200:
        sys.exit(f"1. team key rejected: {me.status_code} {me.text}")
    print(f"1. team key ok: {me.json()}")

    status = api.get("/v1/gateway/openai-key").json()
    stored = any(value is True for value in status.values())
    openai_key = os.environ.get("GATEWAY_OPENAI_KEY")
    if stored:
        print(f"2. gateway already has our OpenAI key: {status}")
    elif openai_key:
        response = api.post("/v1/gateway/openai-key", json={"api_key": openai_key})
        if response.status_code != 200:
            sys.exit(f"2. gateway rejected the OpenAI key: {response.status_code} {response.text}")
        print(f"2. OpenAI key stored in the gateway: {response.json()}")
    else:
        sys.exit(f"2. gateway has no OpenAI key ({status}) and GATEWAY_OPENAI_KEY is empty in .env")

    models = sorted(model.id for model in llm.client().models.list())
    print(f"3. gateway models: {', '.join(models)}")
    if llm.MODEL not in models:
        print(f"   ! LLM_MODEL={llm.MODEL} is not allowed: pick one above and add its price to llm.PRICES")
    elif llm.MODEL not in llm.PRICES:
        print(f"   ! LLM_MODEL={llm.MODEL} has no price in llm.PRICES: add it before going live")
    else:
        print(f"   LLM_MODEL={llm.MODEL} is allowed and priced")

    with poll_slot():  # the live worker may be polling too: never two polls < 5 s apart (penalty, round 48)
        mail = api.get("/v1/mailbox/messages", params={"since_id": 0, "limit": 2})
    mail.raise_for_status()
    data = mail.json()
    items = data.get("messages") or []
    print(f"4. mailbox poll keys: {sorted(data)}; first item keys: {sorted(items[0]) if items else 'no mail yet'}")
    if items:
        print(json.dumps(items[0], indent=2, ensure_ascii=False)[:1500])
    if "messages" not in data or "next_since_id" not in data:
        print("   ! the poll response is not shaped like {messages, next_since_id}: adjust inbox.FiveUMailbox.fetch()")


if __name__ == "__main__":
    main()
