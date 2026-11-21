import json

import httpx

from inbox import FiveUMailbox

POLL = {"messages": [
    {"id": 7, "from": "buyer@customer.example", "to": "team@hackloop.mail", "subject": "RFQ", "body": "…",
     "references": [], "attachments": [], "sent_at": "2026-11-21T15:00:00Z"},
    {"id": 9, "from": "buyer@customer.example", "to": "team@hackloop.mail", "subject": "Re: RFQ", "body": "ok",
     "references": [7, 8], "attachments": [], "sent_at": "2026-11-21T15:03:00Z"},
], "next_since_id": 9}


def test_poll_keeps_since_id_threads_by_first_mail_and_replies_in_thread(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=POLL)
        return httpx.Response(201, json={"id": 10, **json.loads(request.content)})

    box = FiveUMailbox(key="team-key", state_file=str(tmp_path / ".since_id"))
    box.http = httpx.Client(base_url="https://5u.test", headers={"X-API-Key": "team-key"},
                            transport=httpx.MockTransport(handler))
    first, reply = box.fetch()
    assert (first["thread_id"], reply["thread_id"]) == (7, 7)  # a reply belongs to the RFQ's thread
    assert box.since_id == 9 and (tmp_path / ".since_id").read_text() == "9"
    assert FiveUMailbox(key="k", state_file=str(tmp_path / ".since_id")).since_id == 9  # survives a restart

    assert box.reply(first, "Our quote") == 10
    sent = json.loads(requests[-1].content)
    assert sent == {"to": "buyer@customer.example", "subject": "Re: RFQ", "body": "Our quote", "in_reply_to": 7}
    assert requests[0].headers["X-API-Key"] == "team-key"
