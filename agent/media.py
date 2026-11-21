"""Voice memos and videos attached to an RFQ, transcribed into text so DG, totals and constraints see them like a typed
packing list ("Hi, it's Anna, three pallets, 640 kilos, UN 3480 lithium batteries, to Chicago …").

Off by default (MEDIA_READ=on to use it). The 5U gateway turned out to take no audio, so on a Mac (MEDIA_ENGINE=apple,
the default there) macOS transcribes the recording itself: speech_local.py, $0, no gateway call. Only an attachment the backend can't read costs a call: one transcription,
no retry, short timeout, size-capped. The model only writes down what is said; every number still goes through the
same code checks as a typed packing list.

The transcription endpoint takes mp3, mp4, mpeg, mpga, m4a, wav, webm, flac, ogg/oga itself (mp4 and webm VIDEO too:
it uses their sound). Other recordings (mov, mkv, avi, aac, aiff, amr, opus, 3gp, wmv) are converted to mp3 first,
but only when ffmpeg is installed on the machine; otherwise they are skipped and logged.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import llm
import speech_local

MEDIA_READ = os.environ.get("MEDIA_READ", "off").lower() == "on"
MODEL = os.environ.get("MEDIA_MODEL") or "gpt-4o-mini-transcribe"
# The 5U gateway takes no audio (live test Sat 23:01: transcription 404, input_audio 400), so on a Mac the recording
# is transcribed by macOS itself (speech_local.py, $0, no gateway call). MEDIA_ENGINE=gateway keeps the old path.
ENGINE = os.environ.get("MEDIA_ENGINE") or ("apple" if sys.platform == "darwin" else "gateway")
TIMEOUT_S = float(os.environ.get("MEDIA_READ_TIMEOUT", "20"))
MAX_BYTES = int(os.environ.get("MEDIA_MAX_BYTES", str(10_000_000)))  # ~10 min of a phone memo; the API takes 25 MB
MAX_CHARS = 20000
DIRECT = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "flac", "ogg", "oga"}
CONVERT = {"mov", "mkv", "avi", "aac", "aif", "aiff", "amr", "opus", "3gp", "wmv", "m4v", "caf", "wma"}
ALIASES = {"bwf": "wav"}  # Broadcast Wave is a WAV file
# MIDI, FFV1 and DPX carry no speech: nothing to transcribe.
# Spelled-out numbers and codes are what matter: the prompt nudges the model to write them as digits and codes.
PROMPT = ("Air freight request. Write numbers as digits (pieces, kg, cbm, cm, dates), airport codes and UN numbers "
          "as spoken, e.g. 3 pallets, 640 kg, 2.4 cbm, FRA to ORD, UN 3480.")


def _ext(filename: str) -> str:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    return ALIASES.get(ext, ext)


def readable(filename: str) -> bool:
    """A recording we can transcribe here (directly, or after an ffmpeg conversion when ffmpeg exists)."""
    ext = _ext(filename)
    if ENGINE == "apple":  # what macOS can't read (ogg, opus, webm, ...) goes through ffmpeg first
        return ext in speech_local.FORMATS or (is_media(filename) and shutil.which("ffmpeg") is not None)
    return ext in DIRECT or (ext in CONVERT and shutil.which("ffmpeg") is not None)


def label() -> str:
    return "Apple speech recognition" if ENGINE == "apple" else MODEL


def is_media(filename: str) -> bool:
    ext = _ext(filename)
    return ext in DIRECT or ext in CONVERT


_done: dict[str, str] = {}  # attachment key → its text: a resumed RFQ never pays for the same recording twice


def read_once(key: str, filename: str, data: bytes, timeout: float = TIMEOUT_S, hint: str = "") -> tuple[str, float]:
    if key in _done:
        return _done[key], 0.0
    try:
        text, cost = read(filename, data, timeout, hint)
    except Exception:
        _done[key] = ""  # a failed read is not paid for a second time either
        raise
    _done[key] = text
    return text, cost


def read(filename: str, data: bytes, timeout: float = TIMEOUT_S, hint: str = "") -> tuple[str, float]:
    """(transcript, cost in USD). `hint`: the mail's sender, subject and body, to guess the spoken language (apple).
    Raises on any failure: the caller keeps quoting without it."""
    ext = _ext(filename)
    if ext not in DIRECT and ext not in CONVERT:
        raise ValueError(f"{filename}: not an audio or video file")
    if ENGINE == "apple":
        if len(data) > MAX_BYTES:
            raise ValueError(f"{filename}: {len(data)} bytes, more than {MAX_BYTES}")
        if ext not in speech_local.FORMATS:  # ogg/opus/webm/amr/wma: macOS can't read them, ffmpeg makes an mp3
            data, filename = _to_mp3(filename, data, timeout), f"{filename.rsplit('.', 1)[0]}.mp3"
        elif ext != filename.lower().rsplit(".", 1)[-1]:
            filename = f"{filename.rsplit('.', 1)[0]}.{ext}"
        text, info = speech_local.transcribe(filename, data, speech_local.guess_languages(hint), timeout)
        print(f"speech {filename}: {info['locale']} ({info['mode']}), confidence {info['confidence']:.2f}, $0")
        return text[:MAX_CHARS], 0.0
    if ext in CONVERT:
        data, filename = _to_mp3(filename, data, timeout), f"{filename.rsplit('.', 1)[0]}.mp3"
    elif ext != filename.lower().rsplit(".", 1)[-1]:
        filename = f"{filename.rsplit('.', 1)[0]}.{ext}"  # .bwf → .wav, so the API knows the format
    if len(data) > MAX_BYTES:
        raise ValueError(f"{filename}: {len(data)} bytes, more than {MAX_BYTES}")
    text, cost = llm.transcribe(filename, data, MODEL, PROMPT, timeout)
    return text.strip()[:MAX_CHARS], cost


def _to_mp3(filename: str, data: bytes, timeout: float) -> bytes:
    """The sound of a recording the API doesn't take, as a small mono mp3 (ffmpeg, if installed)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError(f"{filename}: needs ffmpeg to be converted, and ffmpeg isn't installed")
    with tempfile.TemporaryDirectory() as folder:
        source, target = os.path.join(folder, "in." + _ext(filename)), os.path.join(folder, "out.mp3")
        with open(source, "wb") as f:
            f.write(data)
        subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-i", source, "-vn", "-ac", "1", "-ar", "16000",
                        "-b:a", "32k", "-t", "900", target], check=True, timeout=timeout, capture_output=True)
        with open(target, "rb") as f:
            return f.read()
