"""Post-mortem of one session: what would the quote gate have said about the quote we sent? No LLM, sends nothing.

Use it on a rejected round: the reason code from /v1/board/me + this output tell you which rule is missing.
Then add the round to evals/traps.json (mail, attachment, expected behaviour) so it never comes back.

Run (from agent/, backend on BACKEND_URL):
    uv run --env-file ../.env python postmortem.py 42                 session 42, mail as stored in its events
    uv run --env-file ../.env python postmortem.py 42 --mail 2261     + that 5U mail's attachments (read-only GET)
"""

import argparse
import os

import httpx

import gate
from attachments import _texts


def attachment_texts(mail_id: str) -> tuple[dict, list[str]]:
    """The 5U mail and its attachment texts. Plain GETs: never touches .since_id, never sends."""
    http = httpx.Client(base_url=os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai"),
                        headers={"X-API-Key": os.environ["FIVEU_API_KEY"]}, timeout=20)
    mail = http.get(f"/v1/mailbox/messages/{mail_id}").raise_for_status().json()
    texts = []
    for a in mail.get("attachments") or []:
        data = http.get(f"/v1/mailbox/messages/{mail_id}/attachments/{a['id']}").raise_for_status().content
        texts.append("\n".join(_texts(a.get("filename") or "", data)))
        print(f"attachment {a.get('filename')}: {len(texts[-1])} characters read"
              + ("" if texts[-1] else " (format not read: pdf/image)"))
    return mail, texts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("session", type=int)
    ap.add_argument("--mail", help="5U message id of the RFQ, to read its attachments")
    args = ap.parse_args()
    backend = httpx.Client(base_url=os.environ.get("BACKEND_URL", "http://localhost:8000"), timeout=10)
    session = backend.get(f"/api/sessions/{args.session}").raise_for_status().json()
    events = backend.get(f"/api/sessions/{args.session}/events").raise_for_status().json()
    kinds = lambda k: [e for e in events if e["kind"] == k]  # noqa: E731
    mail = (kinds("mail_in")[:1] or [{"data": {}}])[0]["data"]
    texts = []
    if args.mail:
        mail, texts = attachment_texts(args.mail)
    priced = (kinds("priced")[-1:] or [{"data": {}}])[0]["data"]
    sent = (kinds("quote_sent")[-1:] or [{"data": {}}])[0]["data"]
    rfq = dict(session.get("rfq") or {})
    if not priced.get("chosen"):
        print("No priced event with a chosen option: the gate had nothing to check.")
        return
    verdict = gate.review(rfq, priced, mail, texts)
    _, more = gate.finish(sent.get("body") or "", {**verdict, "sentences": []}, rfq)
    print(f"Session {args.session}: {rfq.get('origin')} → {rfq.get('destination')}, {rfq.get('ask')}, "
          f"sent {priced['chosen']['carrier']} EUR {priced['chosen']['total']:,.2f}")
    for f in verdict["findings"] + more:
        print(f"  {f['level'].upper():5} {f['code']}: {f['text']}")
    if not verdict["findings"] + more:
        print("  The gate finds nothing: the trap is new. Add a rule to gate.py and a case to evals/traps.json.")
    if verdict["chosen"] is not priced["chosen"]:
        print(f"  The gate would quote {verdict['chosen']['carrier']} EUR {verdict['chosen']['total']:,.2f} instead")
    if verdict["hold"]:
        print("  The gate would have HELD this quote for a person (auto-send at GATE_AUTO_SEND_SECONDS).")


if __name__ == "__main__":
    main()
