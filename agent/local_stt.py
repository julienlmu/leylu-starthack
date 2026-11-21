"""Voice-message RFQs (R67, R71): transcribed on this machine with mlx-whisper (5U allows local speech-to-text).

LOCAL_STT=off switches it off; STT_PYTHON is the interpreter that has mlx_whisper (default ~/.leylu-stt/bin/python);
STT_TIMEOUT_S caps it (default 25). Any failure returns "" and the RFQ goes the written-details way (DETAILS_ASK).
"""
import os
import subprocess
import tempfile
from pathlib import Path

LOCAL_STT = os.environ.get("LOCAL_STT", "on").lower() != "off"
PYTHON = os.path.expanduser(os.environ.get("STT_PYTHON", "~/.leylu-stt/bin/python"))
MODEL = os.environ.get("STT_MODEL", "mlx-community/whisper-large-v3-turbo")
TIMEOUT_S = float(os.environ.get("STT_TIMEOUT_S", "25"))
AUDIO = (".mp3", ".wav", ".m4a", ".ogg", ".oga", ".aac", ".flac", ".webm", ".mp4", ".amr", ".opus")
SCRIPT = "import sys, mlx_whisper; print(mlx_whisper.transcribe(sys.argv[1], path_or_hf_repo=sys.argv[2])['text'])"


def available(name: str) -> bool:
    return LOCAL_STT and name.lower().endswith(AUDIO) and Path(PYTHON).exists()


def transcribe(name: str, data: bytes) -> str:
    suffix = Path(name).suffix or ".mp3"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(data)
            path = handle.name
        out = subprocess.run([PYTHON, "-c", SCRIPT, path, MODEL], capture_output=True, text=True,
                             timeout=timeout_for(path))
        return tidy(out.stdout.strip()) if out.returncode == 0 else ""
    except Exception as error:  # timeout, missing model, …: the written-details ask takes over
        print(f"local transcription of {name} failed: {type(error).__name__}: {error}")
        return ""
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


POSTCODE = __import__("re").compile(r"\b(\d{2})[.\s](\d{3})(?=,?\s+[A-ZÄÖÜ])")


UN_NUMBER = __import__("re").compile(r"\b(?:you\s*n|u\.?\s*n\.?|you\s+and|you\s+en)\s*(\d{4})\b",
                                    __import__("re").I)


def tidy(text: str) -> str:
    """Whisper writes spoken postcodes as "80.331 München" / "60 311 Francfort" (the zone lookup needs 80331) and
    hears "UN 3480" as "you N3480" / "u n 3480" / "you and 3480" (the DG check needs "UN 3480")."""
    return UN_NUMBER.sub(r"UN \1", POSTCODE.sub(r"\1\2", text))


def timeout_for(path: str) -> float:
    """A 58 s memo took 16.8 s (model load included): allow 20 s + 0.5 s per second of audio, at most 90 s, never
    less than STT_TIMEOUT_S. Duration from ffprobe; unknown → STT_TIMEOUT_S."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=5)
        seconds = float(out.stdout.strip())
    except Exception:
        return TIMEOUT_S
    return max(TIMEOUT_S, min(90.0, 20.0 + 0.5 * seconds))
