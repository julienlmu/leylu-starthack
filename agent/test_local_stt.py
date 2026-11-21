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
