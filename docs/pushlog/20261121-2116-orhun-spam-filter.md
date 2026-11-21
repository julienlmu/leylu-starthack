# Spam mails are ignored, rules only (21:09 alert)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/spam-filter
- What changed: agent/router.py: a new-thread mail with no attachment, no shipment signal at all (weight/dims/pieces units, NxN, IATA pair, quote/rate/RFQ/freight/shipment/cargo/pickup/airport/ready on, German equivalents, UN number) and a spam word (newsletter, unsubscribe, % off, click here, out of office, automatic reply, verify your account, wire transfer, …) routes to "spam": no reply, no LLM, no person. SPAM_FILTER=off switches it off.
- How verified: agent 547 passed: all 53 RFQ mails of day one (agent/evals/real_rfqs_day1.json) are not spam; review probes with spam words plus a shipment stay RFQs; marketing, auto-reply and phishing mails without a shipment are spam
