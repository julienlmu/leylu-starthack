# Credential requests get a fixed refusal, never an RFQ path (R49)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/secret-decline
- What changed: agent/rfq_agent.py: a mail that asks to send/share API keys, gateway keys, passwords, tokens or logins (the secret is the object of a send verb within four words), with no attachment and no shipment or quote words (kg/lbs/t/cbm/pieces/crates/boxes/cartons/colli, NxNxN dims, an IATA pair, quote/rate/RFQ/freight/shipment), gets secret_decline_text; stage done, outcome lost, no person, no LLM. SECRET_DECLINE=off switches it off (it is off live until this review fix is checked).
- How verified: agent 488 passed: R49's mail declined without the reader; seven real RFQs stay RFQs, including the review's four ("PDF is password protected…", "…send the login for your tracking portal", "…a token for the API if you have one", "…our portal login is in the SLI") and any mail with an attachment
