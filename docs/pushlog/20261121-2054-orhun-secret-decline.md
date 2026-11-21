# Credential requests get a fixed refusal, never an RFQ path (R49)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/secret-decline
- What changed: agent/rfq_agent.py: a mail that asks to send/share API keys, gateway keys, passwords, tokens or logins and has no shipment data (no kg/cbm/pieces/pallets) gets secret_decline_text (we never share credentials by email, use the official channel), stage done, no person, no LLM. SECRET_DECLINE=off switches it off.
- How verified: agent 488 passed (R49's mail declined without the reader; three real RFQs mentioning an API or a key account stay RFQs)
