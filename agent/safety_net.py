"""SAFETY_NET (default on; off = no last resort, as before): no RFQ ends with zero reply.

Unknown traps end the same way: a session that sits in "pricing" with nothing sent while the RFQ expires (session 164:
an import nobody priced, session 125: paused, resumed at T+4:27, never quoted). At T+SAFETY_NET_AT_SECONDS (320) after
the RFQ was sent, if nothing at all went to the customer in that thread and no person holds it, one last reply goes out:
- a priced option for the request (the fallback's pricing with earlier trucker bids, the gate's fixes): that quote;
- else an honest decline with no amount ("we can't offer a reliable price for this request; an air export from
  Germany with weight and destination, we quote right away").

Never when: anything was sent in the thread (quote, question, decline; by us or by a person), the session is paused or
closed (lookalike, spam, declined), we wait for the customer's answer, or the mail gave none of origin, destination
and weight (a sales pitch or a "new mail address" mail is no request to answer).
Why 320 s and not 270: the replay over all 189 past sessions. At 270 it would have fired before a person's own quote
in won session 66 (T+4:54) and a person's reply in session 1 (T+5:14). At 320 it fires only on 125 and 164, the two
RFQs that got nothing at all.
"""

import os
import re
import threading
import time

ON = os.environ.get("SAFETY_NET", "on").lower() != "off"
AT_SECONDS = float(os.environ.get("SAFETY_NET_AT_SECONDS", "320"))
LATEST_SECONDS = 345  # the RFQ expires at 6:00 after it was sent: a later reply can't reach 5U in time

_replied: set = set()
_lock = threading.Lock()


class Recording:
    """The worker's mailbox, noting every thread we replied in (the CRM is the second look, after a restart)."""

    def __init__(self, box):
        self.box = box

    def reply(self, mail: dict, body: str, subject: str | None = None, attachments: list | None = None):
        result = self.box.reply(mail, body, **({"subject": subject} if subject else {}),
                                **({"attachments": attachments} if attachments else {}))
        with _lock:
            _replied.add(str(mail.get("thread_id")))
        return result

    def __getattr__(self, name):
        return getattr(self.box, name)


def replied(thread_id) -> bool:
    with _lock:
        return str(thread_id) in _replied


# a routed event that is itself a reply or a deliberate silence ("asked the customer", "declined with the fixed text",
# "no reply (lookalike address), nothing sent", "Spam: … no reply", "closed")
QUIET = re.compile(r"\basked\b|declined|nothing sent|no reply|spam|closed|lookalike", re.I)


def quiet_reason(session: dict | None, events: list[dict]) -> str | None:
    """Why the net stays out of this session, or None: it fires."""
    if not session:
        return "no session"
    if session.get("paused"):
        return "paused by a person"
    if session.get("quote") or session.get("booking"):
        return "quoted"
    if session.get("stage") == "done" or str(session.get("outcome") or "open").lower() != "open":
        return "closed"
    rfq = session.get("rfq") or {}
    if rfq.get("awaiting"):
        return "waiting for the customer's answer"
    customer = str(session.get("customer") or "").lower()
    for e in events:
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        if e.get("kind") in ("quote_sent", "declined"):
            return "a reply went out"
        if e.get("kind") == "intervened" and "Reply sent" in (e.get("text") or ""):
            return "a person replied"
        if e.get("kind") != "mail_in" and customer and str(data.get("to") or "").lower() == customer:
            return "a reply went out"
        if e.get("kind") == "routed" and QUIET.search(e.get("text") or ""):
            return "answered or closed on purpose"
    weight = any(p.get("weight_kg") for p in rfq.get("pieces") or [])
    if not (rfq.get("origin") or rfq.get("destination") or weight):
        return "no request in it (no origin, destination or weight)"
    return None


TEXTS = {
    "en": ("Hello,\n\nthank you for your request. Unfortunately we can't offer you a reliable price for this one. If "
           "it is an air export from Germany, send us the weight and the destination and we'll quote right away."),
    "de": ("Guten Tag,\n\nvielen Dank für Ihre Anfrage. Leider können wir Ihnen dafür keinen verlässlichen Preis "
           "anbieten. Wenn es ein Luftfracht-Export ab Deutschland ist, senden Sie uns Gewicht und Zielort, dann "
           "bekommen Sie sofort ein Angebot."),
    "fr": ("Bonjour,\n\nmerci pour votre demande. Malheureusement, nous ne pouvons pas vous proposer un prix fiable "
           "pour celle-ci. S'il s'agit d'un export aérien depuis l'Allemagne, envoyez-nous le poids et la destination "
           "et nous vous faisons une offre tout de suite."),
    "es": ("Hola:\n\ngracias por su solicitud. Lamentablemente no podemos ofrecerle un precio fiable para esta. Si es "
           "una exportación aérea desde Alemania, envíenos el peso y el destino y se la cotizamos enseguida."),
    "it": ("Buongiorno,\n\ngrazie per la richiesta. Purtroppo non possiamo offrirle un prezzo affidabile per questa. Se "
           "si tratta di un'esportazione aerea dalla Germania, ci invii il peso e la destinazione e le facciamo subito "
           "un'offerta."),
    "tr": ("Merhaba,\n\ntalebiniz için teşekkürler. Maalesef bu talep için size güvenilir bir fiyat veremiyoruz. "
           "Almanya'dan bir hava kargo ihracatıysa ağırlığı ve varış yerini gönderin, hemen fiyat verelim."),
}


def decline_text(language: str | None) -> str:
    import short_mail  # one full sign-off for every customer mail
    lang = (language or "en")[:2].lower()
    lang = lang if lang in TEXTS else "en"
    return TEXTS[lang] + "\n\n" + short_mail._sign(lang)


def watch(mail: dict, box, api) -> None:
    """One per RFQ (its own thread): waits until T+AT_SECONDS, then the last look and, if nothing went out, the reply."""
    from rfq_agent import sent_at
    wait = sent_at(mail) + AT_SECONDS - time.time()
    if wait > 0:
        time.sleep(wait)
    try:
        fire(mail, box, api)
    except Exception as error:  # the net itself must never take the worker down
        print(f"safety net failed for thread {mail.get('thread_id')}: {type(error).__name__}: {error}")


def _still_open(session_id: int, mail: dict, api) -> bool:
    """The last look right before a send: a person may be replying by hand, a late path may just have sent."""
    if replied(mail.get("thread_id")):
        return False
    return quiet_reason(api.session(session_id), api.events(session_id)) is None


def fire(mail: dict, box, api) -> str | None:
    """The net's check and reply. Returns what it did ("quote" / "decline") or None."""
    from backend import now
    from inbox import reply_data
    import rfq_agent
    import shapes
    if not ON or replied(mail.get("thread_id")):
        return None
    if time.time() - rfq_agent.sent_at(mail) > LATEST_SECONDS:
        return None
    session = api.find(mail["thread_id"])
    if not session or quiet_reason(session, api.events(session["id"])):
        return None
    session_id, rfq = session["id"], session.get("rfq") or {}
    priceable = rfq.get("origin") and rfq.get("destination") and rfq.get("pieces") \
        and all(p.get("weight_kg") for p in rfq["pieces"]) \
        and not (shapes.MULTI_SHIPMENT == "hold" and shapes.several_shipments(mail))
    chosen, result = None, {}
    if priceable:
        try:
            result = api.price(rfq, session.get("bids") or [], fallback=True)
            chosen = result.get("chosen")
        except Exception as error:
            api.event(session_id, "error", f"Safety net: pricing failed: {type(error).__name__}: {error}")
    if chosen and chosen.get("total") is not None:
        text = rfq_agent.quote_text(rfq, chosen, mail.get("body"))
        if rfq_agent.FALLBACK_GATE:
            text, chosen = rfq_agent._fallback_gate(session_id, mail, rfq, result, (), api, text, chosen)
        if not _still_open(session_id, mail, api) or time.time() - rfq_agent.sent_at(mail) > LATEST_SECONDS:
            return None
        if chosen is None:  # the gate: a must no option keeps, its question instead of a quote
            rfq_agent._ask_instead(session_id, mail, rfq, text, box, api)
            return "ask"
        rfq_agent._reply_quote(box, mail, text, rfq, chosen, f"S-{session_id}")
        api.update(session_id, stage="quoted", needs_human=False,
                   quote={**chosen, "sent_at": now(), "fallback": True, "safety_net": True})
        api.event(session_id, "quote_sent", f"Safety net quote sent at T+{AT_SECONDS:.0f} s (nothing had gone out): "
                  f"{chosen['currency']} {chosen['total']:,.2f} all-in ({(result.get('why') or '')[:120]})",
                  {**reply_data(mail, text), "option": chosen})
        return "quote"
    if not _still_open(session_id, mail, api):
        return None
    import short_mail
    text = short_mail.named(decline_text(rfq.get("language")), rfq, mail.get("body"))
    box.reply(mail, text)
    api.update(session_id, stage="done", outcome="lost", needs_human=False)
    api.event(session_id, "routed", f"Safety net at T+{AT_SECONDS:.0f} s: nothing had gone out and no option priced it: "
              "declined with the fixed text, no price", reply_data(mail, text))
    return "decline"
