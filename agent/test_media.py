"""Voice memos and videos (media.py, MEDIA_READ): transcribed into text for the DG / totals / constraint checks, off by
default, paid once, never stopping the quote."""
import types

import pytest

import llm
import media
import speech_local
import rfq_agent
from dg import dg_info

MEMO = "Hi, it's Anna. Three pallets, 640 kg, 2.4 cbm, Munich to Chicago, UN 3480 lithium ion batteries, class 9."


class Box:
    def attachment(self, mail, attachment):
        return b"\x00fake-audio" * 10


class Api:
    def __init__(self):
        self.events = []

    def attachment_text(self, name, content_b64):
        return ""  # the backend can't read a recording

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append(text)


def mail(name="memo.m4a"):
    return {"id": 9, "attachments": [{"id": 1, "filename": name}]}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    media._done.clear()
    monkeypatch.setattr(media, "ENGINE", "gateway")  # these tests are about the gateway path; apple ones set it
    monkeypatch.setattr(speech_local, "transcribe", lambda *a, **k: pytest.fail("never runs the real recognizer"))


def test_off_by_default_nothing_is_transcribed(monkeypatch):
    assert media.MEDIA_READ is False
    monkeypatch.setattr(media, "read", lambda *a, **k: pytest.fail("no transcription while MEDIA_READ is off"))
    assert rfq_agent._attachment_texts(1, mail(), Box(), Api()) == [""]


@pytest.mark.parametrize("name", ["memo.m4a", "memo.mp3", "memo.wav", "memo.bwf", "memo.ogg", "memo.flac",
                                  "clip.mp4", "clip.webm"])
def test_on_a_recording_becomes_text_its_cost_counts_and_it_is_paid_once(monkeypatch, name):
    monkeypatch.setattr(media, "MEDIA_READ", True)
    calls = []
    monkeypatch.setattr(llm, "transcribe", lambda f, d, m, p, t: (calls.append(f) or MEMO, 0.0021))
    costs, api = [], Api()
    texts = rfq_agent._attachment_texts(1, mail(name), Box(), api, costs)
    assert texts == [MEMO] and costs == [0.0021] and any("transcribed" in e for e in api.events)
    assert calls[0].endswith(".wav") if name.endswith(".bwf") else calls[0] == name
    rfq_agent._attachment_texts(1, mail(name), Box(), Api(), costs)  # the pickup answer resumes the same RFQ
    assert len(calls) == 1 and costs == [0.0021, 0.0]
    assert dg_info(texts[0])  # the DG check sees the spoken UN number


def test_a_failed_or_slow_transcription_never_stops_the_quote(monkeypatch):
    monkeypatch.setattr(media, "MEDIA_READ", True)
    monkeypatch.setattr(llm, "transcribe", lambda *a: (_ for _ in ()).throw(TimeoutError("slow")))
    assert rfq_agent._attachment_texts(1, mail(), Box(), Api()) == [""]


def test_a_format_that_needs_ffmpeg_is_skipped_and_logged_without_it(monkeypatch):
    monkeypatch.setattr(media, "MEDIA_READ", True)
    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    monkeypatch.setattr(llm, "transcribe", lambda *a: pytest.fail("no call without ffmpeg"))
    api = Api()
    assert rfq_agent._attachment_texts(1, mail("clip.mov"), Box(), api) == [""]
    assert any("needs ffmpeg" in e for e in api.events)


def test_limits():
    with pytest.raises(ValueError):
        media.read("song.mid", b"MThd")  # MIDI carries no speech
    with pytest.raises(ValueError):
        media.read("memo.mp3", b"\x00" * (media.MAX_BYTES + 1))


def test_transcription_cost_from_tokens_or_minutes(monkeypatch):
    def fake_client(usage, text="3 pallets"):
        create = lambda **k: types.SimpleNamespace(text=text, usage=usage)
        api = types.SimpleNamespace(audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create)))
        return types.SimpleNamespace(with_options=lambda **k: api)

    monkeypatch.setattr(llm, "client", lambda: fake_client(types.SimpleNamespace(input_tokens=1000, output_tokens=50)))
    assert llm.transcribe("m.mp3", b"x", "gpt-4o-mini-transcribe", "", 5) == ("3 pallets", (1000 * 3 + 50 * 5) / 1e6)
    monkeypatch.setattr(llm, "client", lambda: fake_client(types.SimpleNamespace(seconds=120)))
    assert llm.transcribe("m.mp3", b"x", "whisper-1", "", 5)[1] == pytest.approx(0.012)
    with pytest.raises(KeyError):
        llm.transcribe("m.mp3", b"x", "unpriced-model", "", 5)


# --- MEDIA_ENGINE=apple: macOS transcribes (the gateway takes no audio); the recognizer itself is mocked here ---

@pytest.mark.parametrize("name", ["memo.m4a", "memo.mp3", "memo.wav", "memo.caf", "memo.flac", "clip.mp4", "clip.mov"])
def test_apple_a_recording_becomes_text_for_free_with_the_mails_language_first(monkeypatch, name):
    monkeypatch.setattr(media, "MEDIA_READ", True)
    monkeypatch.setattr(media, "ENGINE", "apple")
    monkeypatch.setattr(llm, "transcribe", lambda *a, **k: pytest.fail("no gateway call"))
    calls = []

    def fake(filename, data, languages, timeout):
        calls.append((filename, languages[0], timeout))
        return "Drei Paletten, 640 kg, Lithium-Ionen-Batterien, UN 3480, Klasse 9", {"confidence": 0.77,
                                                                                   "locale": "de-DE", "mode": "server"}

    monkeypatch.setattr(speech_local, "transcribe", fake)
    api, the_mail = Api(), {**mail(name), "from": "anna@meyer-industrie.de", "body": "Bitte siehe Sprachnachricht."}
    costs = []
    texts = rfq_agent._attachment_texts(1, the_mail, Box(), api, costs)
    assert texts == ["Drei Paletten, 640 kg, Lithium-Ionen-Batterien, UN 3480, Klasse 9"] and costs == [0.0]
    assert calls[0][0] == name and calls[0][1] == "de-DE" and 0 < calls[0][2] <= media.TIMEOUT_S
    assert any("Apple speech recognition" in e for e in api.events)
    assert rfq_agent._attachment_texts(1, the_mail, Box(), api) == texts and len(calls) == 1  # paid / run once


def test_apple_a_failed_recognition_keeps_quoting(monkeypatch):
    monkeypatch.setattr(media, "MEDIA_READ", True)
    monkeypatch.setattr(media, "ENGINE", "apple")
    monkeypatch.setattr(speech_local, "transcribe", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("not allowed")))
    assert rfq_agent._attachment_texts(1, mail("memo.m4a"), Box(), Api()) == [""]


def test_apple_reads_what_macos_reads_and_ogg_still_needs_ffmpeg(monkeypatch):
    monkeypatch.setattr(media, "ENGINE", "apple")
    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    assert all(media.readable(f"x.{ext}") for ext in ("m4a", "mp3", "wav", "caf", "aiff", "flac", "mp4", "mov", "3gp"))
    assert not media.readable("x.ogg") and not media.readable("x.opus") and not media.readable("x.webm")


def test_guess_languages_from_the_mail():
    guess = speech_local.guess_languages
    assert guess("anna@meyer-industrie.de\nBitte siehe die Sprachnachricht, viele Grüße")[0] == "de-DE"
    assert guess("thomas@durand.fr\nBonjour, voir le message vocal. Merci pour le devis")[0] == "fr-FR"
    assert guess("yelda@arcelik.com.tr\nMerhaba, sesli mesaj için teşekkürler")[0] == "tr-TR"
    assert guess("你好，请听语音留言")[0] == "zh-CN"
    assert guess("info@hackloop.mail\nPlease find the voice memo attached.")[0] == "en-US"
    assert guess("")[0] == "en-US" and len(set(guess(""))) == len(speech_local.LANGUAGES)


@pytest.mark.parametrize("heard, written", [
    ("lithium ion batteries you N3480 class nine", "lithium ion batteries UN 3480 class nine"),
    ("Lithium Ionen Batterien in 3480 Klasse neun", "Lithium Ionen Batterien UN 3480 Klasse neun"),
    ("baterías de iones de litio un 3480 clase nueve", "baterías de iones de litio UN 3480 clase nueve"),
    ("U.N. 1845 dry ice", "UN 1845 dry ice"),
    ("ready in 2026, 3 pallets", "ready in 2026, 3 pallets"),  # a year stays a year
    ("in 640 kg", "in 640 kg"),
])
def test_spoken_un_numbers_are_written_back(heard, written):
    assert speech_local.normalize(heard) == written


# --- MEMO_WINS: a voice memo's figures win over the mail's (a correction in the memo was lost before) ---

def _memo_rfq(tmp_path, monkeypatch, transcript, missing_without_memo=(), memo_read_fails=False):
    """One RFQ whose mail says 2 crates / 440 lb and whose memo `transcript` is read; read_request is mocked: it
    reads 3 crates / 640 kg only when the memo is in the body it gets."""
    import base64
    from bids import BidBoard
    from extract import to_rfq
    from inbox import FixtureMailbox
    from test_rfq_agent import CARRIERS, MAIL, OPTION, RAW, FakeApi
    monkeypatch.setattr(media, "MEDIA_READ", True)
    monkeypatch.setattr(media, "read_once", lambda key, name, data, timeout=None, hint="": (transcript, 0.0))
    bodies = []

    def fake_read(mail):
        bodies.append(mail["body"])
        memo = rfq_agent.MEMO_HEAD in mail["body"]
        if memo and memo_read_fails:
            raise TimeoutError("gateway slow")
        piece = {**RAW["pieces"][0], **({"count": 3, "weight": 640} if memo else {})}
        raw = {**RAW, "pieces": [piece], "weight_unit": "kg" if memo else "lb", "pickup_address": None}
        return {"rfq": to_rfq(raw)[0], "missing": [] if memo else list(missing_without_memo), "cost": 0.0001,
                "model": "m", "escalated": None}

    monkeypatch.setattr(rfq_agent, "read_request", fake_read)
    box, api = FixtureMailbox(tmp_path), FakeApi({"options": [OPTION], "chosen": OPTION})
    api.attachment_text = lambda name, content: ""
    att = [{"filename": "memo.m4a", "content_base64": base64.b64encode(b"\x00audio").decode()}]
    rfq_agent.handle_rfq({**MAIL, "attachments": att}, box, api, BidBoard(), CARRIERS, cutoff_s=0.1)
    return api, bodies


def test_memo_wins_a_correction_in_the_memo_reaches_the_price(tmp_path, monkeypatch):
    api, bodies = _memo_rfq(tmp_path, monkeypatch, "Sorry, correction: it's three crates, 640 kg in total.")
    pieces = api.data["extracted"]["pieces"]
    assert sum(p["count"] * p["weight_kg"] for p in pieces) == pytest.approx(640)
    assert len(bodies) == 2 and rfq_agent.MEMO_HEAD in bodies[1] and "640 kg" in bodies[1]
    assert any(u.get("llm_cost_usd") == pytest.approx(0.0002) for u in api.updates)  # mail read + memo read
    assert "quote_sent" in api.events


def test_memo_wins_no_numbers_in_the_memo_no_extra_call(tmp_path, monkeypatch):
    api, bodies = _memo_rfq(tmp_path, monkeypatch, "Hi, it's Anna, please see my mail, thanks.")
    assert len(bodies) == 1 and "quote_sent" in api.events


def test_memo_wins_switched_off_keeps_the_old_path(tmp_path, monkeypatch):
    monkeypatch.setattr(rfq_agent, "MEMO_WINS", False)
    api, bodies = _memo_rfq(tmp_path, monkeypatch, "Correction: three crates, 640 kg.")
    assert len(bodies) == 1  # the mail had everything: the attachment re-read doesn't run either


def test_memo_wins_a_memo_only_rfq_is_read_once_more_not_twice(tmp_path, monkeypatch):
    """Mail: 'see the voice memo' (weight missing): the memo read replaces the old attachment re-read, one call."""
    api, bodies = _memo_rfq(tmp_path, monkeypatch, "Three crates, 640 kg, Munich to New York.", ("weight",))
    assert len(bodies) == 2 and api.data["extracted"]["pieces"][0]["count"] == 3


def test_memo_wins_a_failed_memo_read_keeps_the_mails_reading(tmp_path, monkeypatch):
    api, bodies = _memo_rfq(tmp_path, monkeypatch, "Correction: three crates, 640 kg.", memo_read_fails=True)
    assert len(bodies) == 2 and "quote_sent" in api.events
    assert api.data["extracted"]["pieces"][0]["count"] == 2  # the mail's reading
