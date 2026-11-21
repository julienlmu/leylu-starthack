import local_stt


def test_only_audio_with_the_interpreter_present(monkeypatch, tmp_path):
    fake = tmp_path / "python"
    fake.write_text("")
    monkeypatch.setattr(local_stt, "PYTHON", str(fake))
    assert local_stt.available("voice-message.mp3") and not local_stt.available("packing-list.pdf")
    monkeypatch.setattr(local_stt, "LOCAL_STT", False)
    assert not local_stt.available("voice-message.mp3")


def test_a_failing_transcriber_returns_empty(monkeypatch):
    monkeypatch.setattr(local_stt, "PYTHON", "/nonexistent/python")
    assert local_stt.transcribe("voice-message.mp3", b"ID3") == ""



def test_spoken_postcodes_are_joined_but_weights_are_not():
    assert local_stt.tidy("Abholung 80.331 München, nach JFK") == "Abholung 80331 München, nach JFK"
    assert local_stt.tidy("Enlèvement 60 311 Francfort, destination") == "Enlèvement 60311 Francfort, destination"
    assert local_stt.tidy("The gross weight is 1,804 kilos and 12 345 pieces") == "The gross weight is 1,804 kilos and 12 345 pieces"



def test_long_memos_get_more_time(monkeypatch):
    class Out:
        def __init__(self, s):
            self.stdout = s
    monkeypatch.setattr(local_stt.subprocess, "run", lambda *a, **k: Out("140.0"))
    assert local_stt.timeout_for("x.mp3") == 90.0
    monkeypatch.setattr(local_stt.subprocess, "run", lambda *a, **k: Out("58.0"))
    assert local_stt.timeout_for("x.mp3") == 49.0
    monkeypatch.setattr(local_stt.subprocess, "run", lambda *a, **k: Out(""))
    assert local_stt.timeout_for("x.mp3") == local_stt.TIMEOUT_S



def test_misheard_un_numbers_are_restored():
    for heard in ("lithium batteries, you N3480", "lithium batteries, u n 3480", "lithium batteries, you and 3480"):
        assert local_stt.tidy(heard) == "lithium batteries, UN 3480", heard
    assert local_stt.tidy("we can send you 2000 kg") == "we can send you 2000 kg"


def test_cargo_numbers_are_never_un_numbers():
    """#192's rule on whisper's output too: no DG word nearby, or a unit right after, is cargo."""
    for heard in ("total weight in 1500 kg", "we ship in 1200 cartons", "envío un 1000 kg", "you and 2000 kg",
                  "for you n 1500 pieces"):
        assert "UN " not in local_stt.tidy(heard), heard
    assert local_stt.tidy("Lithiumbatterien, in 3480") == "Lithiumbatterien, UN 3480"


def test_one_engine_per_memo(monkeypatch):
    """MEDIA_READ on → media.py only; off → mlx-whisper only. Never both for one recording."""
    import rfq_agent

    calls = []
    monkeypatch.setattr(local_stt, "available", lambda name: True)
    monkeypatch.setattr(local_stt, "transcribe", lambda *a: calls.append("mlx") or "3 pallets 640 kg FRA to ORD")
    monkeypatch.setattr(rfq_agent.media, "readable", lambda name: True)
    monkeypatch.setattr(rfq_agent.media, "read_once", lambda *a: calls.append("media") or ("", 0.0))

    class Box:
        def attachment(self, mail, attachment):
            return b"ID3"

    class Api:
        def attachment_text(self, *a, **k):
            return ""

        def event(self, *a, **k):
            pass

    mail = {"id": 1, "body": "voice message attached", "attachments": [{"id": 1, "filename": "memo.mp3"}]}
    monkeypatch.setattr(rfq_agent.media, "MEDIA_READ", True)
    rfq_agent._attachment_texts(1, mail, Box(), Api())
    assert calls == ["media"]
    calls.clear()
    monkeypatch.setattr(rfq_agent.media, "MEDIA_READ", False)
    costs = []
    texts = rfq_agent._attachment_texts(1, mail, Box(), Api(), costs)
    assert calls == ["mlx"] and costs == [0.0] and "640 kg" in texts[0]
