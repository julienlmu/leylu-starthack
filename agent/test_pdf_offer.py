"""Round 75 `no_pdf_offer`: the quote also goes out as a PDF with the same single amount."""
import base64
import re

import pytest

import pdf_offer
import rfq_agent
from inbox import FixtureMailbox

MAIL = {"id": 7, "thread_id": 7, "from": "anna@customer.example", "subject": "RFQ MUC-ORD",
        "body": "Please send your offer as a PDF.", "attachments": []}
TEXT = "Hi Anna,\n\nLumen Air Cargo can fly it for EUR 2,345.67 all in.\n\nThanks,\nLena"


def test_every_quote_carries_the_same_text_as_a_pdf(tmp_path):
    box = FixtureMailbox(tmp_path)
    rfq_agent._reply_quote(box, MAIL, TEXT, {"origin": "MUC", "destination": "ORD", "pieces": []})
    [sent] = box.sent
    [pdf] = sent["attachments"]
    data = base64.b64decode(pdf["content_base64"])
    assert pdf["filename"].endswith(".pdf") and data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert re.findall(rb"\d[\d,.]*\.\d\d", data) == [b"2,345.67"] and sent["body"] == TEXT


@pytest.mark.parametrize("mode, body, attached", [("off", "as a PDF please", False), ("asked", "as a PDF please", True),
                                                  ("asked", "no format wish", False), ("always", "no format wish", True)])
def test_the_switch(tmp_path, monkeypatch, mode, body, attached):
    monkeypatch.setattr(pdf_offer, "PDF_OFFER", mode)
    box = FixtureMailbox(tmp_path)
    rfq_agent._reply_quote(box, {**MAIL, "body": body}, TEXT, {"origin": "MUC", "destination": "ORD", "pieces": []})
    assert ("attachments" in box.sent[0]) == attached


def test_a_pdf_problem_never_costs_the_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_offer, "build", lambda text: 1 / 0)
    box = FixtureMailbox(tmp_path)
    rfq_agent._reply_quote(box, MAIL, TEXT, {"origin": "MUC", "destination": "ORD", "pieces": []})
    assert box.sent[0]["body"] == TEXT and "attachments" not in box.sent[0]


def test_a_mailbox_without_attachments_still_gets_the_quote():
    class OldBox:
        def __init__(self):
            self.sent = []

        def reply(self, mail, body, subject=None):
            self.sent.append(body)

    box = OldBox()
    rfq_agent._reply_quote(box, MAIL, TEXT, {"origin": "MUC", "destination": "ORD", "pieces": []})
    assert box.sent == [TEXT]


def test_if_5u_refuses_the_attachment_the_quote_still_goes_out(tmp_path):
    import httpx

    import inbox
    sent = []

    def handler(request):
        body = __import__("json").loads(request.content)
        sent.append(body)
        if "attachments" in body:
            return httpx.Response(422, json={"detail": "attachments: unexpected field"})
        return httpx.Response(201, json={"id": 99})

    box = inbox.FiveUMailbox(key="k", state_file=str(tmp_path / "since"))
    box.http = httpx.Client(base_url="http://5u.test", transport=httpx.MockTransport(handler))
    assert box.reply(MAIL, TEXT, attachments=[{"filename": "q.pdf", "content_base64": "JVBERg=="}]) == 99
    assert len(sent) == 2 and "attachments" not in sent[1] and sent[1]["body"] == TEXT
