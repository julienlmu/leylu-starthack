"""SANCTIONS: a shipment to Russia, Belarus, Iran, North Korea, Syria or occupied Crimea / Donetsk / Luhansk is declined
politely with a fixed text, no price, no carrier asked (an EU forwarder must not ship there; a quote would also have no
lane). Rules only, no LLM. Read from the extracted destination and from destination wording in the mail ("final
destination Tehran", "re-export to Russia", "nach Moskau"), never from a goods description or an old shipment
("Russian dolls", "we used to ship to Moscow"). SANCTIONS=off: priced as before.
"""

import os
import re

SANCTIONS = os.environ.get("SANCTIONS", "on").lower() != "off"

AIRPORTS = {"SVO", "DME", "VKO", "LED", "KZN", "SVX", "OVB", "AER", "KRR", "ROV", "UFA", "KJA", "VVO", "KGD", "MSQ",
            "IKA", "THR", "MHD", "SYZ", "IFN", "TBZ", "FNJ", "DAM", "ALP", "LTK", "SIP"}
PLACES = (r"russia|russland|russie|rusia|russian\s+federation|russische\w*\s+f[öo]deration|belarus|wei(?:ß|ss)russland|"
          r"bi[eé]lorussie|iran|islamic\s+republic\s+of\s+iran|north\s+korea|nordkorea|cor[ée]e\s+du\s+nord|dprk|"
          r"syria|syrien|syrie|crimea|krim|crim[ée]e|donetsk|donezk|luhansk|lugansk|"
          r"moscow|moskau|moscou|mosc[úu]|st\.?\s*petersburg|sankt\s+petersburg|saint[- ]p[ée]tersbourg|novosibirsk|"
          r"yekaterinburg|jekaterinburg|kazan|kaliningrad|minsk|tehran|teheran|t[ée]h[ée]ran|mashhad|isfahan|tabriz|"
          r"shiraz|pyongyang|pj[öo]ngjang|damascus|damaskus|damas|aleppo|simferopol|sevastopol|sewastopol")
PLACE = re.compile(rf"\b(?:{PLACES})\b", re.I)
# the mail sends the goods there: "to Moscow", "final destination: Tehran", "nach Minsk", "re-export to Iran"
TOWARDS = re.compile(
    r"\b(?:to|into|nach|vers|hacia|naar|destination|final\s+destination|end\s+destination|ultimate\s+destination|"
    r"end[- ]?user\s+in|consignee\s+in|deliver(?:y|ed)?\s+to|re-?export(?:ed)?\s+to|onward\s+to|bestimmungsort|"
    r"endbestimmung\w*|zielort|ziel|empf[äa]nger\s+in|destino)\b\W{0,4}(?:[\w.-]+\W{1,3}){0,2}?(?:" + PLACES + r")\b"
    # "Syria Street", "our Moscow office": a street or an office named after the place is no destination
    # (a warehouse, plant or branch there still receives the goods: still declined)
    r"(?!\W{1,2}(?:street|st\b|str\w*|road|rd\b|avenue|ave\b|lane|way|blvd|boulevard|gasse|weg|platz|office|"
    r"team|desk|hq|headquarters|büro))",
    re.I)
PAST = re.compile(r"\b(?:used\s+to|previously|in\s+the\s+past|until\s+20\d\d|before\s+20\d\d|no\s+longer|früher|"
                  r"bis\s+20\d\d|not\s+to|nicht\s+nach|except|au(?:ß|ss)er)\b", re.I)


def sanctioned(rfq: dict, mail: dict) -> str | None:
    """The sanctioned place this request ships to, or None."""
    if not SANCTIONS:
        return None
    destination = str(rfq.get("destination") or "").strip()
    if destination.upper() in AIRPORTS:
        return destination.upper()
    if PLACE.search(destination):
        return PLACE.search(destination).group(0)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"):
        if (m := TOWARDS.search(sentence)) and not PAST.search(sentence):
            return PLACE.search(m.group(0)).group(0)
    return None


TEXTS = {
    "en": ("Hello,\n\nthank you for your request. Unfortunately we can't offer transport to {place}: shipments there "
           "fall under the current EU sanctions, so we don't handle them. If you have shipments to other destinations, "
           "I'm happy to quote them right away.\n\nBest regards,\nLena\nLeylü Air Freight"),
    "de": ("Guten Tag,\n\nvielen Dank für Ihre Anfrage. Leider können wir keinen Transport nach {place} anbieten: "
           "Sendungen dorthin fallen unter die aktuellen EU-Sanktionen, deshalb übernehmen wir sie nicht. Für Sendungen "
           "in andere Länder mache ich Ihnen gern sofort ein Angebot.\n\nMit freundlichen Grüßen\nLena\nLeylü Air Freight"),
}


def decline_text(place: str, language: str | None) -> str:
    return TEXTS.get((language or "en")[:2].lower(), TEXTS["en"]).format(place=place)
