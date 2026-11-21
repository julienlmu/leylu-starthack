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
