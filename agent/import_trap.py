"""IMPORT_DECLINE (default on; off = priced as before): session 164 asked airport-to-airport NRT → HAM. That is an
import into Germany: we only sell air exports from German airports, so no lane priced it, the session went to a person
with 0 options and waited on nobody. Now such a request gets an honest decline at once, with no price: we handle air
exports from German airports only, and we'd gladly quote one.

Caught (rules only, no LLM):
- the extracted origin is an airport outside Germany (NRT, PVG, JFK …), unless the pickup is a door-to-port address
  near a German zone (FOREIGN_PICKUP flies it from the nearest German airport);
- or the mail says it is an import: "import from Japan", "we are importing", "import shipment", "inbound from",
  "we are the receiver / consignee / importer", "our supplier hands over in Tokyo", "Import aus", "Einfuhr",
  "wir sind der Empfänger". Never the words around an export: "import duties / customs / clearance / licence at
  destination", "important", "the importer of record in the US is …".
"""

import os
import re

ON = os.environ.get("IMPORT_DECLINE", "on").lower() != "off"
# LANE_DECLINE (R159, default on): every carrier asked answered "we do not serve this lane" and no sheet or portal rate
# priced it → the same honest decline (another text) right after the round, instead of a person with 0 options.
LANE = os.environ.get("LANE_DECLINE", "on").lower() != "off"

# German airports with cargo traffic (the kit's six export airports first) and the city codes customers write.
GERMAN = {"FRA", "MUC", "HAM", "DUS", "CGN", "STR", "BER", "TXL", "SXF", "LEJ", "HAJ", "NUE", "BRE", "DTM", "FMO",
          "HHN", "PAD", "SCN", "FDH", "FKB", "NRN", "KSF", "ERF", "RLG", "LBC", "GWT", "HDF", "XFW", "FMM", "DRS",
          "AGB", "SZW", "BRV", "ZQW", "EDDF", "EDDM", "EDDH", "EDDL", "EDDK", "EDDS", "EDDB", "EDDP", "QPP", "BWE"}

_DUTY = r"(?!\s*(?:dut|tax|vat|custom|clear|licen|permit|fee|regul|document|paper|declar|formalit|restrict|ban|quota))"
SAYS_IMPORT = re.compile(
    r"\b(?:import(?:ing|ed)?\s+(?:from|out\s+of|this|these|it|goods|cargo|shipment|consignment|via|by\s+air)\b|"
    r"(?:an?|this|our|the)\s+import\s+(?:shipment|consignment|order|job|request|load)\b|"
    r"we\s*(?:'re|\s+are|\s+will\s+be)\s+(?:importing|the\s+(?:importer|receiver|consignee|receiving\s+party))\b|"
    r"inbound\s+(?:shipment\s+)?from\b|"
    r"importsendung|import\s+aus\b|einfuhr(?:\s+aus)?\b|wir\s+(?:sind|wären)\s+(?:der\s+|die\s+)?(?:empf[äa]nger|"
    r"importeur)\b|"
    r"import(?:ation)?\s+depuis\b|importaci[óo]n\s+desde\b|importazione\s+da\b|ithalat\w*)",
    re.I)
# "our supplier hands over in Tokyo": an import only when the origin isn't a German airport (it can be our own warehouse)
SUPPLIER = re.compile(r"\b(?:our|the)\s+(?:supplier|vendor|manufacturer|factory|shipper)\s+(?:will\s+)?hand(?:s|ing)?\s+"
                      r"(?:it\s+|them\s+|the\s+goods\s+)?over\s+(?:at|in)\b", re.I)
EXPORT_WORDS = re.compile(r"\b(?:export|ausfuhr|exportation|exportaci[óo]n|ihracat)\w*\b" + _DUTY, re.I)


def caught(rfq: dict, mail: dict) -> str | None:
    """Why this request is an import (a short reason for the event), or None."""
    if not ON:
        return None
    origin = str(rfq.get("origin") or "").strip().upper()
    near_zone = bool(_zone(rfq.get("pickup")))
    if re.fullmatch(r"[A-Z]{3}", origin) and origin not in GERMAN and not near_zone:
        return f"origin {origin} is not a German airport"
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    if (m := SAYS_IMPORT.search(text) or (origin not in GERMAN and SUPPLIER.search(text))) \
            and not EXPORT_WORDS.search(text):
        return f'the mail says "{m.group(0).strip()}"'
    return None


def _zone(pickup: dict | None):
    """The German pickup zone (a German postcode, or FOREIGN_PICKUP's nearest zone for Innsbruck): flown from Germany."""
    from carriers import pickup_zone
    try:
        return pickup_zone(pickup)
    except Exception:
        return None


TEXTS = {
    "en": ("Hello,\n\nthank you for your request. Unfortunately this one isn't something we can quote: we only handle "
           "air freight exports from German airports, not imports into Germany or shipments that start abroad. If you "
           "have a shipment leaving from Germany, I'm happy to quote it right away."),
    "de": ("Guten Tag,\n\nvielen Dank für Ihre Anfrage. Diese Sendung können wir leider nicht anbieten: Wir übernehmen "
           "nur Luftfracht-Exporte ab deutschen Flughäfen, keine Importe nach Deutschland und keine Sendungen, die im "
           "Ausland beginnen. Für eine Sendung ab Deutschland mache ich Ihnen gern sofort ein Angebot."),
    "fr": ("Bonjour,\n\nmerci pour votre demande. Malheureusement, nous ne pouvons pas la coter : nous ne traitons que "
           "le fret aérien à l'export depuis les aéroports allemands, pas les importations vers l'Allemagne ni les "
           "envois qui partent de l'étranger. Pour un envoi au départ de l'Allemagne, je vous fais une offre tout de "
           "suite."),
    "es": ("Hola:\n\ngracias por su solicitud. Lamentablemente no podemos cotizarla: solo gestionamos exportaciones de "
           "carga aérea desde aeropuertos alemanes, no importaciones a Alemania ni envíos que salen del extranjero. Si "
           "tiene un envío con salida desde Alemania, se lo cotizo enseguida."),
    "it": ("Buongiorno,\n\ngrazie per la richiesta. Purtroppo non possiamo quotarla: gestiamo solo esportazioni di merci "
           "via aerea dagli aeroporti tedeschi, non importazioni in Germania né spedizioni che partono dall'estero. Per "
           "una spedizione in partenza dalla Germania le faccio subito un'offerta."),
    "tr": ("Merhaba,\n\ntalebiniz için teşekkürler. Maalesef bu gönderi için fiyat veremiyoruz: yalnızca Almanya'daki "
           "havalimanlarından yapılan hava kargo ihracatlarını üstleniyoruz, Almanya'ya ithalatları veya yurt dışında "
           "başlayan gönderileri değil. Almanya'dan çıkacak bir gönderiniz varsa hemen fiyat verebilirim."),
}


def decline_text(language: str | None) -> str:
    import short_mail  # one full sign-off for every customer mail
    lang = (language or "en")[:2].lower()
    lang = lang if lang in TEXTS else "en"
    return TEXTS[lang] + "\n\n" + short_mail._sign(lang)


LANE_TEXTS = {
    "en": ("Hello,\n\nthank you for your request. Unfortunately we can't quote this one: none of our airline partners "
           "serves this route. If you have another shipment leaving from Germany, I'm happy to quote it right away."),
    "de": ("Guten Tag,\n\nvielen Dank für Ihre Anfrage. Leider können wir sie nicht anbieten: Keiner unserer "
           "Airline-Partner bedient diese Strecke. Für eine andere Sendung ab Deutschland mache ich Ihnen gern sofort "
           "ein Angebot."),
    "fr": ("Bonjour,\n\nmerci pour votre demande. Malheureusement, nous ne pouvons pas la coter : aucune de nos "
           "compagnies partenaires ne dessert cette route. Pour un autre envoi au départ de l'Allemagne, je vous fais "
           "une offre tout de suite."),
    "es": ("Hola:\n\ngracias por su solicitud. Lamentablemente no podemos cotizarla: ninguna de nuestras aerolíneas "
           "asociadas cubre esta ruta. Si tiene otro envío con salida desde Alemania, se lo cotizo enseguida."),
    "it": ("Buongiorno,\n\ngrazie per la richiesta. Purtroppo non possiamo quotarla: nessuna delle nostre compagnie "
           "partner serve questa rotta. Per un'altra spedizione in partenza dalla Germania le faccio subito un'offerta."),
    "tr": ("Merhaba,\n\ntalebiniz için teşekkürler. Maalesef bu gönderi için fiyat veremiyoruz: çalıştığımız "
           "havayollarından hiçbiri bu hatta uçmuyor. Almanya'dan çıkacak başka bir gönderiniz varsa hemen fiyat "
           "verebilirim."),
}


def lane_text(language: str | None) -> str:
    import short_mail
    lang = (language or "en")[:2].lower()
    lang = lang if lang in LANE_TEXTS else "en"
    return LANE_TEXTS[lang] + "\n\n" + short_mail._sign(lang)
