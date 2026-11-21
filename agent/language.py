"""The language a customer wrote in, read by code (no LLM). Two uses, both feeding main's one mechanism (#189/#190):
rfq["language"] picks the template, short_mail fills it, facts are filled by code, a finished mail never goes to a model.

- wanted(mail): the language to answer a mail that has no extraction (tracking questions): an explicit "please reply in
  English" first, else the language of the customer's own text (quoted history and the signature block left out),
  else None (the caller falls back to the session's rfq language, then English).
- script_language(text): a writing system other than Latin that clearly dominates (R72: a Chinese RFQ with one English
  closing line). extract.read_request uses it only when the model's mail language disagrees and nobody asked for a
  reply language: then the model misread it.
"""

import os
import re
import unicodedata

# REPLY_LANGUAGE=off: extract keeps the model's mail language, tracking answers stay English (as before)
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
        if ranked[0] >= 3 and ranked[0] >= 1.4 * (ranked[1] if len(ranked) > 1 else 0):  # 3+ words: "no ... non-toxic" is no Italian
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


def wanted(mail: dict) -> str | None:
    """The language our reply to `mail` should be in, or None when we can't tell (then nothing is changed)."""
    own = own_text(mail.get("body"))
    return asked_language(own) or detect(own) or (detect(mail.get("subject")) if len(own.strip()) < 20 else None)


def script_language(text: str | None) -> str | None:
    """A non-Latin writing system that makes up most of the customer's own text ("zh", "ja", "ko", "ru", "ar", ...),
    else None. Latin-script languages are left to the model: it reads them better than word lists."""
    best = detect(own_text(text))
    return best if best and best not in _WORDS else None
