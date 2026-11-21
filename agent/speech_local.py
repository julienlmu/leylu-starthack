"""Voice memos transcribed on the Mac itself with Apple's speech recognition (media.py, MEDIA_ENGINE=apple).

Why: the 5U gateway takes no audio (live test Sat 23:01: /audio/transcriptions → 404, an input_audio part to
gpt-6-luna → 400 "text or image_url only"). Apple's recognizer is part of macOS: no package, no gateway call, $0.
English and Turkish run on the device; other languages run on the device once their dictation model is downloaded
(System Settings → Keyboard → Dictation → Languages), otherwise on Apple's servers (needs internet).

The recognizer only writes down what is said; numbers still go through the same code checks as a typed packing list.
It doesn't know the language, so it tries the likely ones in order (the mail's language and sender domain first)
and keeps the first transcript whose mean word confidence reaches THRESHOLD (live test: right language 0.64–0.85,
wrong one 0.18–0.30).

One-time setup on the live Mac: `uv run python speech_local.py --build`, then click "Allow" in the speech
recognition dialog (a command-line tool can't get that permission, so the tool is built as a tiny .app).
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "speech", "stt.swift")
PLIST = os.path.join(HERE, "speech", "Info.plist")
APP = os.path.expanduser(os.environ.get("STT_APP", "~/Library/Application Support/leylu-stt/LeyluSTT.app"))
THRESHOLD = 0.6
# read by macOS itself (AVFoundation); ogg/opus/webm/amr/wma are not, they need ffmpeg first (media.py converts)
FORMATS = {"wav", "mp3", "m4a", "aac", "aif", "aiff", "caf", "flac", "mp4", "mov", "m4v", "3gp"}
LANGUAGES = ["en-US", "de-DE", "fr-FR", "es-ES", "it-IT", "tr-TR", "nl-NL", "pl-PL", "pt-PT", "zh-CN", "ja-JP",
             "ru-RU", "ar-SA"]
_STOPWORDS = {
    "de-DE": "und der die das wir ist nicht bitte mit für von ein eine ihr sie gruß grüße angebot",
    "fr-FR": "le la les des nous pour avec est une un vous bonjour merci devis cordialement",
    "es-ES": "el los las para con por que una usted hola gracias cotización saludos",
    "it-IT": "il gli per con che una sono buongiorno grazie preventivo cordiali saluti",
    "tr-TR": "ve bir için ile bu merhaba teşekkürler lütfen fiyat saygılarımla",
    "nl-NL": "het een van voor met wij niet graag offerte groeten",
    "pl-PL": "się nie jest dla prosimy dzień dobry wycena pozdrawiam",
    "pt-PT": "não uma para com obrigado cotação cumprimentos olá",
    "en-US": "the and for with please we our you quote thanks regards",
}
_DOMAINS = {"de": "de-DE", "at": "de-DE", "ch": "de-DE", "fr": "fr-FR", "be": "fr-FR", "es": "es-ES", "mx": "es-ES",
            "it": "it-IT", "tr": "tr-TR", "nl": "nl-NL", "pl": "pl-PL", "pt": "pt-PT", "br": "pt-PT", "cn": "zh-CN",
            "jp": "ja-JP", "ru": "ru-RU", "sa": "ar-SA", "ae": "ar-SA"}
_SCRIPTS = [("zh-CN", r"[一-鿿]"), ("ja-JP", r"[぀-ヿ]"), ("ru-RU", r"[Ѐ-ӿ]"),
            ("ar-SA", r"[؀-ۿ]")]
# "UN 3480" comes back as "you N3480", "U N 3480", "in 3480" (de), "un 3480" (es/it): written back as a UN number.
# "in"/"un" + a year ("in 2026") stays as it is.
_UN = re.compile(r"\b(?:you\s*N|U\.?\s*N\.?)\s*-?\s*(\d{4})\b|\b(?:un|in|ün)\s+(?!(?:19|20)\d\d\b)([0-3]\d{3})\b", re.I)
_lock = threading.Lock()  # one recognition at a time: parallel ones fail on the server side (error 209/216)


def available() -> bool:
    return sys.platform == "darwin" and (os.path.isdir(APP) or shutil.which("xcrun") is not None)


def guess_languages(hint: str = "") -> list[str]:
    """Locales to try, most likely first: the script and words of the mail, then its sender's domain, then English."""
    text = (hint or "").lower()
    scores = {code: sum(text.count(f" {w} ") for w in words.split()) for code, words in _STOPWORDS.items()}
    for code, pattern in _SCRIPTS:
        scores[code] = scores.get(code, 0) + 5 * len(re.findall(pattern, hint or ""))
    domain = re.search(r"@[\w.-]+\.([a-z]{2,3})\b", text)
    if domain and domain[1] in _DOMAINS:
        scores[_DOMAINS[domain[1]]] = scores.get(_DOMAINS[domain[1]], 0) + 3
    ranked = [code for code, score in sorted(scores.items(), key=lambda s: -s[1]) if score > 0]
    return list(dict.fromkeys(ranked + ["en-US"] + LANGUAGES))


def normalize(text: str) -> str:
    return _UN.sub(lambda m: f"UN {m[1] or m[2]}", text)


def _hash() -> str:
    digest = hashlib.sha256()
    for path in (SOURCE, PLIST):
        with open(path, "rb") as f:
            digest.update(f.read())
    return digest.hexdigest()[:16]


def build() -> str:
    """The .app, compiled once (and again when stt.swift changes). Ad-hoc signed; macOS asks for the permission once."""
    stamp = os.path.join(os.path.dirname(APP), "built-from")
    if os.path.isdir(APP) and os.path.exists(stamp) and open(stamp).read() == _hash():
        return APP
    with tempfile.TemporaryDirectory() as folder:
        app = os.path.join(folder, "LeyluSTT.app")
        os.makedirs(os.path.join(app, "Contents", "MacOS"))
        shutil.copy(PLIST, os.path.join(app, "Contents", "Info.plist"))
        subprocess.run(["xcrun", "swiftc", "-O", SOURCE, "-o", os.path.join(app, "Contents", "MacOS", "stt")],
                       check=True, capture_output=True, timeout=300)
        subprocess.run(["codesign", "-s", "-", "--force", app], check=True, capture_output=True, timeout=60)
        os.makedirs(os.path.dirname(APP), exist_ok=True)
        shutil.rmtree(APP, ignore_errors=True)
        shutil.move(app, APP)
    with open(stamp, "w") as f:
        f.write(_hash())
    return APP


def transcribe(filename: str, data: bytes, languages: list[str], timeout: float) -> tuple[str, dict]:
    """(transcript, {"confidence", "locale", "mode"}). Raises on any failure: the caller keeps quoting without it."""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext not in FORMATS:
        raise ValueError(f"{filename}: macOS can't read .{ext}")
    if not available():
        raise RuntimeError("Apple speech recognition needs macOS with Xcode command line tools")
    app = build()
    with _lock, tempfile.TemporaryDirectory() as folder:
        source, out = os.path.join(folder, f"memo.{ext}"), os.path.join(folder, "out.txt")
        with open(source, "wb") as f:
            f.write(data)
        budget = max(1.0, timeout - 1.5)  # `open` and the app's start take ~1 s
        subprocess.run(["open", "-W", "-n", app, "--args", source, out, ",".join(languages), str(THRESHOLD),
                        f"{budget:.1f}"], capture_output=True, timeout=timeout + 5)
        if not os.path.exists(out):
            raise RuntimeError("no transcript (is speech recognition allowed for LeyluSTT?)")
        line = open(out, encoding="utf-8").read().rstrip("\n")
    if line.startswith("ERROR\t"):
        raise RuntimeError(line.split("\t", 1)[1])
    confidence, locale, mode, text = line.split("\t", 3)
    return normalize(text.strip()), {"confidence": float(confidence), "locale": locale, "mode": mode}


if __name__ == "__main__":
    if "--build" in sys.argv:
        print(f"built {build()}: run it once on a memo to get the permission dialog")
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[-1]):
        path = sys.argv[-1]
        print(transcribe(os.path.basename(path), open(path, "rb").read(), guess_languages(), 30))
