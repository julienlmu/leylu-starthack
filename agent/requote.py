"""REQUOTE (rfq_agent.requote_after_change, R86/R87): which customer replies after our quote change the shipment.

Rules only, no LLM. kind(text, rfq):
- "requote": a change word ("changed", "updated", "instead", "now is", "geändert" …) or our own question just before
  it, plus a weight in the mail (kg/lbs); the figures must differ from what we quoted ("is the 1,317 kg we quoted
  incl. pallets?" or "thanks for the update" with our own numbers is no change).
- "ask": a change of pieces / volume / dimensions without a weight ("now 5 pieces, 8.18 cbm"): one short question for
  the figures, never a guessed weight; their answer is re-quoted (rfq.requote_asked).
- None: anything else; "can you also quote 2 pallets to ORD" / "another shipment" is a new request, never a change of
  this one (a person, as before).
grounded(): the new reading has every number the customer wrote (total or per piece), else we ask instead of quoting
a misread. A second unclear change goes to a person (MAX_ASKS).
"""

import re

MAX_ASKS = 1
REQUOTE_ASK = re.compile(r"\b(?:chang\w*|updat\w*|correct\w*|amend\w*|revis\w*|instead|now (?:is|are|it'?s)|(?:is|are) now|"
                         r"final packing list|ge(?:ä|ae)ndert|aktualisier\w*|korrigier\w*|neue[ns]? angebot)\b", re.I)
# The new weight must be in the mail (R86/R87: "5 pieces, 1317 kg gross weight, 8.18 cbm")
NEW_FIGURES = re.compile(r"\b\d[\d.,']*\s*(?:kg|kgs|kilos?|kilograms?|lbs?)\b", re.I)
THANKS_UPDATE = re.compile(r"\bthanks?(?: you)? for (?:the|your) update\b", re.I)
# Another shipment, never a change of this one; "instead" can't override these ("also need 300 kg … instead of sea").
NEW_SHIPMENT = re.compile(r"\b(?:also\s+(?:quote|price|need|send|have|get|ship)|(?:another|a\s+second|one\s+more|a\s+new|"
                          r"a\s+separate)\s+(?:shipment|order|quote|request|offer|consignment)|separately|"
                          r"zusätzlich\w*|ebenfalls|noch\s+eine\s+(?:sendung|anfrage)|weitere\s+(?:sendung|anfrage))\b", re.I)
# Weaker: "another pallet, 1,317 kg instead of 900 kg" is a change.
ALSO = re.compile(r"\b(?:as\s+well|in\s+addition|additionally|another)\b", re.I)
INSTEAD = re.compile(r"\b(?:instead|statt\w*|rather\s+than|replac\w*)\b", re.I)
_NUM = r"(\d{1,3}(?:[.,' ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
KG = re.compile(_NUM + r"\s*(?:kg|kgs|kilos?|kilograms?)\b", re.I)
LBS = re.compile(_NUM + r"\s*(?:lbs?|pounds)\b", re.I)
M3 = re.compile(_NUM + r"\s*(?:cbm|m3|m³|cubic\s+met(?:er|re)s?|kubikmeter)\b", re.I)
PIECES = re.compile(r"\b(\d{1,4})\s*(?:pcs|pieces?|pallets?|plts?|cartons?|ctns?|crates?|boxes|cases?|colli|kolli|"
                    r"packages?|pkgs?|stück|stk|paletten?|packstücke)\b", re.I)
DIMS = re.compile(r"\b\d{2,4}(?:[.,]\d+)?\s*[x×*]\s*\d{2,4}(?:[.,]\d+)?\s*[x×*]\s*\d{2,4}(?:[.,]\d+)?\b", re.I)
CODE = re.compile(r"\b[A-Z]{3}\b")

ASK = {
    "en": "Thanks for the update. So that I quote exactly the new shipment: could you send me the total number of "
          "pieces, the total gross weight in kg and the volume in cbm (or the dimensions of each piece)? I'll send "
          "the new all-in price right away.",
    "de": "Danke für die Änderung. Damit ich genau die neue Sendung anbiete: Können Sie mir bitte die Anzahl der "
          "Packstücke, das Gesamtgewicht in kg und das Volumen in cbm (oder die Maße je Packstück) schicken? Den neuen "
          "Gesamtpreis bekommen Sie dann sofort.",
    "fr": "Merci pour la mise à jour. Pour chiffrer exactement le nouvel envoi, pourriez-vous m'envoyer le nombre total "
          "de colis, le poids brut total en kg et le volume en m³ (ou les dimensions de chaque colis) ? Je vous envoie "
          "le nouveau prix tout compris tout de suite.",
    "es": "Gracias por la actualización. Para cotizar exactamente el nuevo envío, ¿podría enviarme el número total de "
          "bultos, el peso bruto total en kg y el volumen en m³ (o las medidas de cada bulto)? Le envío enseguida el "
          "nuevo precio todo incluido.",
    "it": "Grazie per l'aggiornamento. Per quotare esattamente la nuova spedizione, può inviarmi il numero totale di "
          "colli, il peso lordo totale in kg e il volume in m³ (o le misure di ogni collo)? Le mando subito il nuovo "
          "prezzo tutto incluso.",
    "nl": "Bedankt voor de update. Zodat ik precies de nieuwe zending kan prijzen: kunt u mij het totale aantal colli, "
          "het totale brutogewicht in kg en het volume in m³ (of de afmetingen per collo) sturen? Dan stuur ik meteen "
          "de nieuwe all-in prijs.",
    "pt": "Obrigada pela atualização. Para cotar exatamente o novo envio, pode enviar-me o número total de volumes, o "
          "peso bruto total em kg e o volume em m³ (ou as dimensões de cada volume)? Envio-lhe logo o novo preço com "
          "tudo incluído.",
    "tr": "Güncelleme için teşekkürler. Yeni gönderiyi tam olarak fiyatlayabilmem için toplam koli sayısını, toplam "
          "brüt ağırlığı (kg) ve hacmi (m³) ya da her kolinin ölçülerini gönderebilir misiniz? Yeni her şey dahil "
          "fiyatı hemen gönderirim.",
    "pl": "Dziękuję za aktualizację. Żebym wycenił dokładnie nową przesyłkę: czy mogą Państwo przesłać łączną liczbę "
          "sztuk, łączną wagę brutto w kg i objętość w m³ (albo wymiary każdej sztuki)? Nową cenę all-in wyślę od razu.",
    "cs": "Děkuji za aktualizaci. Abych nacenil přesně novou zásilku: můžete mi poslat celkový počet kusů, celkovou "
          "hrubou hmotnost v kg a objem v m³ (nebo rozměry každého kusu)? Novou cenu all-in vám pošlu hned.",
    "sv": "Tack för uppdateringen. För att jag ska kunna prissätta exakt den nya sändningen: kan du skicka totalt antal "
          "kollin, total bruttovikt i kg och volymen i m³ (eller måtten per kolli)? Jag skickar det nya all-in-priset "
          "direkt.",
    "da": "Tak for opdateringen. Så jeg kan prissætte præcis den nye forsendelse: kan du sende mig det samlede antal "
          "kolli, den samlede bruttovægt i kg og volumen i m³ (eller målene på hvert kolli)? Jeg sender den nye "
          "all-in pris med det samme.",
    "nb": "Takk for oppdateringen. Så jeg kan prise akkurat den nye sendingen: kan du sende meg totalt antall kolli, "
          "total bruttovekt i kg og volumet i m³ (eller målene per kolli)? Jeg sender den nye all-in prisen med en gang.",
    "fi": "Kiitos päivityksestä. Jotta voin hinnoitella juuri uuden lähetyksen: voisitteko lähettää kollien "
          "kokonaismäärän, kokonaisbruttopainon kiloina ja tilavuuden kuutioina (tai kunkin kollin mitat)? Lähetän "
          "uuden kokonaishinnan heti.",
    "ja": "更新のご連絡ありがとうございます。新しい貨物を正確にお見積りするため、総個数、総重量（kg）、容積（m³）"
          "（または各梱包の寸法）をお送りいただけますか？新しいオールイン価格をすぐにお送りします。",
    "zh": "感谢您的更新。为了准确报价新的货物，请您提供总件数、总毛重（kg）和体积（m³）（或每件的尺寸），"
          "我会马上发送新的全包价格。",
}


def number(raw: str) -> float:
    """"1,317" / "1.317" / "1 317" → 1317; "8,18" / "8.18" → 8.18; "1,317.50" → 1317.5."""
    raw = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,' ]\d{3})+", raw):
        return float(re.sub(r"[.,' ]", "", raw))
    if m := re.fullmatch(r"(\d{1,3}(?:[.,' ]\d{3})+)[.,](\d+)", raw):
        return float(re.sub(r"[.,' ]", "", m.group(1)) + "." + m.group(2))
    return float(raw.replace(",", "."))


def stated(text: str) -> dict:
    """The cargo figures a mail writes: kg (lbs converted), m3, piece counts, whether it gives dimensions."""
    return {"kg": [number(m) for m in KG.findall(text)] + [round(number(m) * 0.45359237, 1) for m in LBS.findall(text)],
            "m3": [number(m) for m in M3.findall(text)], "pieces": [int(m) for m in PIECES.findall(text)],
            "dims": bool(DIMS.search(text))}


def known(rfq: dict) -> dict:
    """The figures of a reading: total and per-piece kg, the volume, total and per-line counts."""
    pieces = rfq.get("pieces") or []
    kg = sum(int(p.get("count") or 1) * float(p.get("weight_kg") or 0) for p in pieces)
    m3 = rfq.get("volume_m3")
    if m3 is None and pieces and all(p.get("length_cm") and p.get("width_cm") and p.get("height_cm") for p in pieces):
        m3 = sum(int(p.get("count") or 1) * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in pieces) / 1e6
    return {"kg": [x for x in [kg, *(p.get("weight_kg") for p in pieces)] if x],
            "m3": [x for x in [m3] if x],
            "pieces": [x for x in [sum(int(p.get("count") or 1) for p in pieces), *(p.get("count") for p in pieces)] if x]}


def _close(value: float, values: list, tolerance: float) -> bool:
    return any(abs(value - v) <= tolerance * max(abs(v), 1.0) for v in values)


def _differs(said: dict, old: dict) -> bool:
    return (any(not _close(v, old["kg"], 0.01) for v in said["kg"]) or any(not _close(v, old["m3"], 0.02)
                                                                           for v in said["m3"])
            or any(v not in old["pieces"] for v in said["pieces"]))


def kind(text: str, rfq: dict) -> str | None:
    """"requote", "ask" or None for a reply to our open quote."""
    text = THANKS_UPDATE.sub(" ", text or "")
    if NEW_SHIPMENT.search(text) or (ALSO.search(text) and not INSTEAD.search(text)):
        return None  # another shipment, not a change of this one
    asked = bool(rfq.get("requote_asked"))
    if not (asked or REQUOTE_ASK.search(text)):
        return None
    said = stated(text)
    if said["kg"]:
        return "requote" if asked or _differs(said, known(rfq)) or said["dims"] else None
    if said["pieces"] or said["m3"] or said["dims"]:
        return "ask" if asked or said["dims"] or _differs(said, known(rfq)) else None
    return None


def grounded(said: dict, new: dict) -> bool:
    """Every figure the customer wrote is in the new reading (as a total or per piece)."""
    have = known(new)
    return (all(_close(v, have["kg"], 0.01) for v in said["kg"]) and all(_close(v, have["m3"], 0.03) for v in said["m3"])
            and all(v in have["pieces"] for v in said["pieces"]))


def ask_text(rfq: dict) -> str:
    """The question in the customer's language and our one voice (short_mail's greeting and sign-off), no amount."""
    import short_mail
    lang = (rfq.get("language") or "en")[:2].lower()
    lang = short_mail.ALIASES.get(lang, lang)
    lang = lang if lang in ASK else "en"
    return short_mail._mail(lang, rfq.get("contact_name"), ASK[lang])
