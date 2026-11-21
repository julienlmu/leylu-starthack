"""Voice memos and videos (media.py, MEDIA_READ): transcribed into text for the DG / totals / constraint checks, off by
default, paid once, never stopping the quote."""
import types

import pytest

import llm
import media
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
def clean():
    media._done.clear()


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
