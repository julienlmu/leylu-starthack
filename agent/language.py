"""The language a customer wrote in, read by code, and a last check on every reply we send (R72 wrong_language).

R72: Hofmann wrote in Chinese with one English closing line ("Thanks a lot and have a lovely day!") and got an English
quote: rejected `wrong_language`. 5U escalates a trap in the same theme (r10 → r11), so the next one may be Arabic,
Korean, Russian, Hindi, Greek, Hebrew, Thai, a reply in another language than the RFQ, or "please answer in English".

- detect(text): ISO 639-1 code from the writing system (CJK, kana, Hangul, Cyrillic, Arabic, Hebrew, Greek, Thai,
  Devanagari, …) or, for Latin script, from common words and letters; None when unsure. Free, no LLM.
- wanted(mail): the language our reply to this mail must be in: an explicit "please reply in English" first, else the
  language of the customer's own text (quoted history and the signature block left out).
- guard(mail, body): REPLY_LANGUAGE (default on). When our reply is not in that language (a whole mail, or one longer
  line, e.g. an English gate sentence inside a German template), one small gateway call translates it; every amount,
  reference and the DG document names must survive word for word, else the reply goes out as it was.
"""

import os
import re
import unicodedata

REPLY_LANGUAGE = os.environ.get("REPLY_LANGUAGE", "on").lower() != "off"

# Writing systems: (code, characters). Han without kana is Chinese; any kana makes it Japanese.
_SCRIPTS = [
    ("ja", re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")),
    ("zh", re.compile(r"[一-鿿㐀-䶿豈-﫿]")),
    ("ko", re.compile(r"[가-힯ᄀ-ᇿ㄰-㆏]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("ar", re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")),
    ("he", re.compile(r"[֐-׿]")),
    ("el", re.compile(r"[Ͱ-Ͽἀ-῿]")),
    ("th", re.compile(r"[฀-๿]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
    ("bn", re.compile(r"[ঀ-৿]")),
    ("ta", re.compile(r"[஀-௿]")),
    ("ka", re.compile(r"[Ⴀ-ჿ]")),
    ("hy", re.compile(r"[԰-֏]")),
]
_CJK = {"ja", "zh", "ko"}  # one character carries about half a word

# Common short words per Latin-script language (articles, pronouns, prepositions, freight words).
_WORDS = {
    "en": "the and to of for please could would you we our is are with from this be will it can need quote thanks "
          "hello dear kind regards shipment pieces ready pickup cheapest fastest best i us your have an at on by",
    "de": "der die das und ist sind wir sie ihr ihre bitte für mit von nach ein eine einen sehr geehrte damen herren "
          "grüße danke vielen uns zu auf den dem des wäre könnten würden sendung abholung stück günstigste schnellste "
          "freundlichen gruß hallo ich nicht oder auch noch",
    "fr": "le la les et est sont nous vous votre vos pour avec de du des une un bonjour merci cordialement pourriez "
          "envoi enlèvement colis prix au aux sur je pas ou également veuillez madame monsieur",
    "es": "el la los las y es son nosotros usted su para con de del una un hola gracias saludos podría envío recogida "
          "bultos precio por favor estimados que en al lo más",
    "it": "il lo la gli le e è sono noi voi vostro per con di del della una un buongiorno grazie cordiali saluti potreste "
          "spedizione ritiro colli prezzo che non anche più",
    "nl": "de het een en is zijn wij we u uw voor met van naar graag bedankt groeten zending ophalen stuks prijs niet "
          "ook wel kunt zou",
    "pt": "o a os as e é são nós você seu sua para com de do da uma um olá obrigado obrigada cumprimentos poderia envio "
          "recolha volumes preço não também por favor",
    "tr": "ve bir bu için ile lütfen teşekkürler merhaba sayın gönderi fiyat teklif adet hazır en ucuz hızlı bize "
          "bizim olarak var mı mısınız",
    "pl": "i w z na do się jest są dla nie że to proszę dziękuję dzień dobry pozdrawiam przesyłka cena sztuk od po "
          "czy oraz",
    "cs": "a v z na do se je jsou pro ne že to prosím děkuji dobrý den zdravím zásilka cena kusů od po jak také",
    "sk": "a v z na do sa je sú pre nie že to prosím ďakujem dobrý deň zásielka cena kusov od po ako",
    "sv": "och i att det är för med på av en ett vi ni er tack hej hälsningar försändelse pris kolli inte också",
    "da": "og i at det er for med på af en et vi i jeres tak hej hilsen forsendelse pris kolli ikke også",
    "nb": "og i at det er for med på av en et vi dere tak hei hilsen forsendelse pris kolli ikke også",
    "fi": "ja on ovat että se tämä kiitos hei terveisin lähetys hinta kollia ei myös voisitteko meille",
    "hu": "és a az egy is nem hogy van kérem köszönöm üdvözlettel szállítmány ár darab tisztelt",
    "ro": "și în la de cu pe un o este sunt vă vă rog mulțumesc bună ziua expediere preț bucăți pentru",
    "hr": "i u na je su za s se ne da molim hvala lijep pozdrav pošiljka cijena komada od",
    "sl": "in v na je so za z se ne da prosim hvala lep pozdrav pošiljka cena kosov od",
    "id": "dan di ke dari yang untuk dengan ini itu kami anda mohon terima kasih salam pengiriman harga",
    "vi": "và của cho với các là có không chúng tôi bạn xin cảm ơn chào giá hàng",
}
_WORDS = {code: set(words.split()) for code, words in _WORDS.items()}
# Letters only one or two of them use (a strong hint, counted like two words)
_LETTERS = {"de": "ßü", "pl": "łśźżęąń", "cs": "řůě", "sk": "ľĺŕô", "hu": "őű", "ro": "ășțâ", "tr": "ğışİ",
            "es": "ñ¿¡", "pt": "ãõ", "fr": "œàèùëêç", "it": "ìò", "sv": "å", "da": "øæ", "nb": "øæ", "fi": "",
            "vi": "ơưđạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ", "hr": "đ", "sl": "",
            "is": "ðþ"}
_TOKEN = re.compile(r"[^\W\d_]+", re.U)
NAMES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch",
         "pt": "Portuguese", "tr": "Turkish", "pl": "Polish", "cs": "Czech", "sk": "Slovak", "sv": "Swedish",
         "da": "Danish", "nb": "Norwegian", "fi": "Finnish", "hu": "Hungarian", "ro": "Romanian", "hr": "Croatian",
         "sl": "Slovenian", "id": "Indonesian", "vi": "Vietnamese", "ja": "Japanese", "zh": "Chinese",
         "ko": "Korean", "ru": "Russian", "uk": "Ukrainian", "bg": "Bulgarian", "sr": "Serbian", "ar": "Arabic",
         "fa": "Persian", "ur": "Urdu", "he": "Hebrew", "el": "Greek", "th": "Thai", "hi": "Hindi",
         "bn": "Bengali", "ta": "Tamil", "ka": "Georgian", "hy": "Armenian"}


def _cyrillic(text: str) -> str:
    if re.search(r"[іїєґІЇЄҐ]", text):
        return "uk"
    if re.search(r"[ђћџљњЂЋЏЉЊ]", text):
        return "sr"
    if len(re.findall(r"[ъЪ]", text)) > 2 and not re.search(r"[ыЫэЭ]", text):
        return "bg"
    return "ru"


def _arabic(text: str) -> str:
    if re.search(r"[ٹڈڑںے]", text):
        return "ur"
    if re.search(r"[پچژگ]", text):
        return "fa"
    return "ar"


_NORDIC = {"sv", "da", "nb"}


def _nordic(lowered: str, tokens: list[str]) -> str:
    if re.search(r"[äö]", lowered) or {"och", "inte", "är", "gäller", "hälsningar", "tack", "ni"} & set(tokens):
        return "sv"
    if {"dere", "takk", "hei", "oss", "gjerne"} & set(tokens):
        return "nb"
    return "da"


def _scores(text: str) -> dict[str, float]:
    """Weight of each language in the text: script characters, or Latin words of each language."""
    scores: dict[str, float] = {}
    for code, chars in _SCRIPTS:
        n = len(chars.findall(text))
        if n:
            scores[code] = scores.get(code, 0) + (n / 2 if code in _CJK else n / 5)  # ~5 letters per word
    if "ja" in scores and "zh" in scores:  # Japanese writes Han too
        scores["ja"] += scores.pop("zh")
    if "ru" in scores:
        scores[_cyrillic(text)] = scores.pop("ru")
    if "ar" in scores:
        scores[_arabic(text)] = scores.pop("ar")
    latin = [t.lower() for t in _TOKEN.findall(text) if t.isascii() or any("a" <= unicodedata.normalize("NFD", c)[0]
                                                                            <= "z" for c in t.lower())]
    if latin:
        words: dict[str, float] = {}
        for code, vocab in _WORDS.items():
            words[code] = sum(1 for t in latin if t in vocab)
        lowered = text.lower()
        for code, letters in _LETTERS.items():
            if letters and code in words:
                words[code] += 2 * sum(lowered.count(c) for c in letters if c.isalpha()) ** 0.5
        best = max(words, key=words.get)
        ranked = sorted(words.values(), reverse=True)
        top2 = sorted(words, key=words.get, reverse=True)[:2]
        if set(top2) <= _NORDIC and ranked[0] >= 2:  # Swedish / Danish / Norwegian share most short words
            best, ranked = _nordic(lowered, latin), [ranked[0], 0]
        if ranked[0] >= 2 and ranked[0] >= 1.4 * (ranked[1] if len(ranked) > 1 else 0):
            scores[best] = scores.get(best, 0) + len(latin)  # the Latin text counts as that language
        else:
            scores["?latin"] = len(latin)
    return scores


def detect(text: str | None) -> str | None:
    """ISO 639-1 code of the text's main language, or None (too short, or no clear winner)."""
    scores = _scores(text or "")
    if not scores:
        return None
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if best == "?latin" or scores[best] < 2 or scores[best] < 0.6 * total:
        return None
    return best


# The customer's own words: no quoted history, no signature block after the closing line.
# A closing line is the whole line ("Best regards", "Thanks a lot and have a lovely day!"), never "Thanks for the quote".
_CLOSING = re.compile(r"^\s*(?:(?:best|kind|warm|many|with\s+kind)\s+(?:regards|wishes|greetings)|regards|cheers|"
                      r"thanks?(?:\s+(?:a\s+lot|so\s+much|again|in\s+advance))?(?:\s+and\s+have\s+a\s+[\w\s]{0,20}"
                      r"(?:day|week|weekend|evening))?|thank\s+you(?:\s+(?:very\s+much|in\s+advance))?|sincerely|"
                      r"mit\s+freundlichen\s+gr\w*|viele\s+gr\w*|beste\s+gr\w*|liebe\s+gr\w*|cordialement|bien\s+à\s+vous|"
                      r"saludos(?:\s+cordiales)?|atentamente|cordiali\s+saluti|distinti\s+saluti|met\s+vriendelijke\s+groet\w*|"
                      r"groeten|saudações|atenciosamente|pozdrawiam|s\s+pozdravem|med\s+vänliga\s+hälsningar|"
                      r"vänliga\s+hälsningar|med\s+venlig\s+hilsen|ystävällisin\s+terveisin|üdvözlettel|cu\s+stimă|"
                      r"saygılarımla)\s*[,.!]*\s*(?:/.*)?$|^\s*--\s*$", re.I)


def own_text(body: str | None) -> str:
    from inbox import latest_text
    lines = latest_text(body or "").splitlines()
    for i, line in enumerate(lines):
        if i >= 2 and _CLOSING.match(line):
            return "\n".join(lines[:i])
    return "\n".join(lines)


# "Please reply in English", "Antworten Sie bitte auf Englisch", "請用英文回覆": the customer's explicit wish wins.
_LANG_WORDS = {
    "en": r"english|englisch|anglais|ingl[eé]s|inglese|engels|ingilizce|angielsku|anglicky|engelska|engelsk|"
          r"englanniksi|angolul|engleză|英文|英语|英語|영어|английском",
    "de": r"german|deutsch|allemand|alem[aá]n|tedesco|duits|almanca|niemiecku|německy|德语|德文|ドイツ語|독일어|немецком",
    "fr": r"french|französisch|fran[cç]ais|franc[eé]s|francese|frans|fransızca|francusku|法语|フランス語|프랑스어",
    "es": r"spanish|spanisch|espagnol|espa[nñ]ol|spagnolo|spaans|ispanyolca|hiszpańsku|西班牙语|スペイン語",
    "it": r"italian|italienisch|italien|italiano|italiaans|italyanca|意大利语|イタリア語",
    "zh": r"chinese|chinesisch|chinois|chino|cinese|chinees|çince|中文|汉语|漢語|chinesisch",
    "ja": r"japanese|japanisch|japonais|japon[eé]s|giapponese|japans|japonca|日本語|日语",
}
_ASK_LANG = re.compile(
    r"(?:reply|respond|answer|write(?:\s+back)?|communicate|correspond|send\s+(?:your|the)\s+(?:reply|answer|quote|offer))"
    r"(?:\s+(?:to\s+)?(?:us|me))?(?:\s+\w+){0,2}?\s+in\s+(?P<a>\w+)"
    r"|(?:antwort\w*|schreib\w*|kommuni\w*)(?:\s+\w+){0,3}?\s+(?:auf|in)\s+(?P<b>\w+)"
    r"|(?:répond\w*|écri\w*)(?:\s+\w+){0,3}?\s+en\s+(?P<c>\w+)"
    r"|(?:respond\w*|contest\w*|escrib\w*|rispond\w*|scriv\w*)(?:\s+\w+){0,3}?\s+in?\s+(?P<d>\w+)"
    r"|(?:请|請|麻烦|麻煩)?用(?P<e>英文|英语|英語|中文|德语|德文|日语|日語)(?:回复|回覆|答复|答覆|回信|联系|聯繫)"
    r"|(?P<f>英語|日本語|中国語|ドイツ語)で(?:返信|回答|ご連絡)", re.I)


def asked_language(text: str | None) -> str | None:
    """The language the customer explicitly asks us to answer in, else None (ours and extract.REPLY_IN, #189)."""
    for m in _ASK_LANG.finditer(text or ""):
        word = next(g for g in m.groups() if g)
        for code, words in _LANG_WORDS.items():
            if re.fullmatch(rf"(?:{words})", word, re.I):
                return code
    try:
        from extract import reply_language
        return reply_language(None, text or "") or None
    except Exception:
        return None


def mentions(text: str | None, code: str | None) -> bool:
    """The mail names that language at all ("…in English", "Englisch", "英文"): then a reply in it is never changed,
    whatever wording the request had (the model may have read a wish our rules missed)."""
    words = _LANG_WORDS.get(code or "")
    if not words:
        try:
            from extract import LANGUAGE_NAMES
            words = LANGUAGE_NAMES.get(code or "")
        except Exception:
            words = None
    return bool(words and re.search(rf"(?:{words})", text or "", re.I))


def wanted(mail: dict) -> str | None:
    """The language our reply to `mail` should be in, or None when we can't tell (then nothing is changed)."""
    own = own_text(mail.get("body"))
    return asked_language(own) or detect(own) or (detect(mail.get("subject")) if len(own.strip()) < 20 else None)


def for_rfq(mail: dict, rfq: dict) -> str | None:
    """The language the templates should write in when the code disagrees with the model, else None. An explicit
    request always counts; otherwise the model's choice stands when it already differs from the mail's language
    (the model read a "please answer in X" our rules missed, #189)."""
    own = own_text(mail.get("body"))
    if asked := asked_language(own):
        return asked if asked != rfq.get("language") else None
    if rfq.get("mail_language") and rfq.get("language") and rfq["language"][:2] != rfq["mail_language"][:2]:
        return None
    code = detect(own)
    return code if code and code != (rfq.get("language") or "")[:2] else None


_MONEY = re.compile(r"\d[\d,.' ]*[.,]\d{2}\b")
_REFS = re.compile(r"\b(?:BK-[A-Z0-9]{6,}|R-[\w-]{6,}|TRK-\d+|S-\d+)\b")
_KEEP_WORDS = ("Shipper's Declaration for Dangerous Goods", "MSDS")
_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
           "properties": {"text": {"type": "string"}}}


def _off_lines(body: str, target: str) -> bool:
    """A line of 6+ words in another language than the target (an English sentence inside a German mail)."""
    for line in body.splitlines():
        if len(_TOKEN.findall(line)) >= 6 and (lang := detect(line)) and lang != target:
            return True
    return False


def needs_translation(body: str, target: str | None) -> bool:
    if not target or not (body or "").strip():
        return False
    lang = detect(body)
    if lang is None:  # unsure: only a reader of another script who would get (almost) none of it
        script = dict(_SCRIPTS).get(_SCRIPT_OF.get(target, target))
        return bool(script) and len(script.findall(body)) < 5
    return lang != target or _off_lines(body, target)


_SCRIPT_OF = {"uk": "ru", "bg": "ru", "sr": "ru", "fa": "ar", "ur": "ar"}


def translate(body: str, target: str) -> str | None:
    """One gateway call; None when it fails or loses an amount, a reference or a DG document name."""
    import llm
    name = NAMES.get(target, f"the language with ISO code '{target}'")
    try:
        data, cost = llm.chat_json(
            "reply_language",
            f"Translate this email into {name}. Keep it short and natural, like a person wrote it. Keep every number, "
            "amount, currency code, airline name, airport code, booking reference, rate ID and date exactly as written; "
            "keep the words \"Shipper's Declaration for Dangerous Goods\" and \"MSDS\" in English. Keep the line "
            "breaks and the name under the email. Return only the email.",
            body, _SCHEMA, timeout=15, max_tokens=900)
    except Exception as error:
        print(f"reply translation to {target} failed: {type(error).__name__}: {error}")
        return None
    out = ((data or {}).get("text") or "").strip()
    keep = set(_MONEY.findall(body)) | set(_REFS.findall(body)) | {w for w in _KEEP_WORDS if w in body}
    if not out or not all(k in out for k in keep):
        print(f"reply translation to {target} dropped: an amount, reference or DG word changed")
        return None
    if detect(out) not in (target, None):
        return None
    return out


def guard(mail: dict, body: str) -> str:
    """The reply in the customer's language: unchanged when it already is, when we can't tell, or when off."""
    if not REPLY_LANGUAGE:
        return body
    try:
        target = wanted(mail)
        if not needs_translation(body, target):
            return body
        if mentions(mail.get("body"), detect(body)):  # "…please reply in English": our English reply stays
            return body
        return translate(body, target) or body
    except Exception as error:  # the language check must never cost us the reply
        print(f"reply language check skipped: {type(error).__name__}: {error}")
        return body
