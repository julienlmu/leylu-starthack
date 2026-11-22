"""MODE_DECLINE (default on; off = priced as air, as before): a sea, road, rail or courier request is not ours.

The sweep (22 Nov): "sea freight FCL 40' DEHAM to AEJEA", "LTL truck from Stuttgart to Milan", "rail freight Duisburg to
Chengdu", "a document envelope by courier" all got an AIR quote, a price for a service nobody asked for. Session 184
(sea FCL HAM → JEA) was only declined because all 29 carriers refused the lane. Now such a request gets an honest
decline at once, with no amount: we only sell air freight, and we'd gladly quote the shipment by air.

Caught (rules only, no LLM): the mail's subject or text names another mode (sea/ocean freight, FCL/LCL, a 20/40 ft
container, port-to-port, road freight/FTL/LTL, rail freight, courier/parcel service; de/fr/es words too) AND names
air nowhere (air freight, by air, airport, flight, airline, AWB, Luftfracht, …). Every past RFQ with a truck or road
word also said air freight (73, 76, 87, 123, 124: the pickup by truck): none of them is caught.
"""

import os
import re

ON = os.environ.get("MODE_DECLINE", "on").lower() != "off"

NON_AIR = re.compile(
    r"\b(?:sea|ocean)[ -]?freight|\bby (?:sea|ship|vessel|rail|train)\b|\bsee?fracht|\bFCL\b|\bLCL\b|"
    r"\b(?:\d+\s*x\s*)?(?:20|40|45)\s*(?:ft|'|’|foot|feet)?\s*(?:hc|dv|high[- ]cube|dry|reefer)?\s*containers?\b|"
    r"\bcontainer (?:ship|vessel)|\bport[- ]to[- ]port\b|\broad (?:freight|transport|haulage)|\bFTL\b|\bLTL\b|"
    r"\bfull[- ]truck[- ]?load|less[- ]than[- ]truck[- ]?load|stra(?:ß|ss)en(?:transport|güterverkehr)|\bkomplettladung|"
    r"\brail (?:freight|transport)|\bbahn(?:fracht|transport)|\b(?:by|via|per) (?:courier|kurier)|"
    r"\bcourier (?:service|shipment|delivery)|\bkurierdienst|\bexpress parcel|\bparcel service|\bpaketdienst|"
    r"\bfret maritime|\btransporte mar[ií]timo|\bflete mar[ií]timo|\bnavire\b|\bbuque\b", re.I)
AIR = re.compile(
    r"\bair[ -]?(?:freight|cargo|shipment|export|transport|waybill)|\bby air\b|\bvia air\b|\bairport|\bflight|\bairline|"
    r"\bAWB\b|\bluftfracht|\bflughafen|\bflug|\bfret a[ée]rien|\ba[ée]roport|\bcarga a[ée]rea|\ba[ée]reo\b|\ba[ée]rea\b|"
    r"\baereo\b|\bhava kargo|\bhavayolu|\bluchtvracht|\bfrete a[ée]reo|\bULD\b", re.I)


def caught(mail: dict) -> str | None:
    """The other mode the mail names, or None (no other mode, or air named too)."""
    if not ON:
        return None
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    if AIR.search(text):
        return None
    found = NON_AIR.search(text)
    return found.group(0).strip() if found else None


TEXTS = {
    "en": ("Hello,\n\nthank you for your request. Unfortunately this one isn't something we can quote: we only offer "
           "air freight, no sea, road, rail or courier shipments. If you'd like this shipment by air from Germany, I'm "
           "happy to quote it right away."),
    "de": ("Guten Tag,\n\nvielen Dank für Ihre Anfrage. Diese Sendung können wir leider nicht anbieten: Wir bieten nur "
           "Luftfracht an, keine See-, Straßen-, Bahn- oder Kuriersendungen. Wenn Sie die Sendung per Luftfracht ab "
           "Deutschland verschicken möchten, mache ich Ihnen gern sofort ein Angebot."),
    "fr": ("Bonjour,\n\nmerci pour votre demande. Malheureusement, nous ne pouvons pas la coter : nous ne proposons que "
           "le fret aérien, pas de transport maritime, routier, ferroviaire ni de coursier. Si vous souhaitez envoyer "
           "cette marchandise par avion depuis l'Allemagne, je vous fais une offre tout de suite."),
    "es": ("Hola:\n\ngracias por su solicitud. Lamentablemente no podemos cotizarla: solo ofrecemos carga aérea, no "
           "envíos marítimos, por carretera, ferrocarril o mensajería. Si desea enviar esta mercancía por avión desde "
           "Alemania, se la cotizo enseguida."),
    "it": ("Buongiorno,\n\ngrazie per la richiesta. Purtroppo non possiamo quotarla: offriamo solo trasporto aereo, non "
           "spedizioni via mare, su strada, su rotaia o tramite corriere. Se desidera spedire la merce via aerea dalla "
           "Germania, le faccio subito un'offerta."),
    "tr": ("Merhaba,\n\ntalebiniz için teşekkürler. Maalesef bu gönderi için fiyat veremiyoruz: yalnızca hava kargo "
           "hizmeti veriyoruz; deniz, kara, demiryolu veya kurye gönderisi yapmıyoruz. Bu gönderiyi Almanya'dan hava "
           "yoluyla göndermek isterseniz hemen fiyat verebilirim."),
}


def decline_text(language: str | None) -> str:
    import short_mail  # one full sign-off for every customer mail
    lang = (language or "en")[:2].lower()
    lang = lang if lang in TEXTS else "en"
    return TEXTS[lang] + "\n\n" + short_mail._sign(lang)
