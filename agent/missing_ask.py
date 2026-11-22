"""MISSING_ASK (default on; off = a person as before): an RFQ we can read, but without a field we can't price without.

5U: "every hour an edge-case mail arrives where data is missing and you have to find it / ask back". Before this, a
readable mail without its destination, origin or weight went to a person and, at night, got no answer at all (0 points).

What the agent finds by itself first (no question): a repeat of an earlier order (repeat.py), the packing list or a
linked document (weight, volume), a city instead of an airport (airports.py), a town or pickup address instead of an
origin (TOWN_PICKUP), only dims or volume missing (priced on the actual weight), a number without its unit (UNIT_ASK),
a voice message / unreadable file (DETAILS_ASK), door pickup without an address (_ask_for_pickup).

What is left gets ONE short question in the customer's language, naming exactly the fields that are missing (plus the
ready date when the mail has none), no amount, no guess. The answer in the same thread is read together with the
first mail (one more extraction) and quoted at once in the same session; a mail that arrived before the question
(a quick "sorry, forgot: 450 kg") is used right away instead of asking. Only these fields are asked for: anything
else in `missing` (injected numbers, one quote per shipment, odd density) keeps its own handling.
"""

import os
import re

ASK = os.environ.get("MISSING_ASK", "on").lower() != "off"
ASKABLE = ("origin", "destination", "weight", "dimensions or volume")
CORE = {"origin", "destination", "weight"}

# One sentence with "and", never a colon and a bullet list (a list with no human talk around it reads like a form).
INTRO = {
    "en": "Thanks for your request but to give you an all-in price I need a bit more info like {fields}.",
    "de": "Danke für Ihre Anfrage! Für den All-in-Preis brauche ich nur noch {fields}.",
    "fr": "Merci pour votre demande ! Pour vous donner le prix tout compris il me faut encore {fields}.",
    "es": "¡Gracias por su solicitud! Para darle el precio todo incluido solo me falta saber {fields}.",
    "it": "Grazie per la richiesta! Per darle il prezzo all-in mi servono ancora {fields}.",
    "nl": "Bedankt voor uw aanvraag! Voor de all-in prijs heb ik alleen nog {fields} nodig.",
    "pt": "Obrigada pelo seu pedido! Para lhe dar o preço all-in só me falta saber {fields}.",
    "tr": "Talebiniz için teşekkürler! Her şey dahil fiyatı verebilmem için {fields} bilgisine ihtiyacım var.",
}
AND = {"en": "and", "de": "und", "fr": "et", "es": "y", "it": "e", "nl": "en", "pt": "e", "tr": "ve"}
FIELDS = {
    "origin": {"en": "the departure airport or pickup postcode", "de": "den Abflughafen oder die Abhol-Postleitzahl",
               "fr": "l'aéroport de départ ou le code postal d'enlèvement",
               "es": "el aeropuerto de salida o el código postal de recogida",
               "it": "l'aeroporto di partenza o il CAP di ritiro", "nl": "de luchthaven van vertrek of de ophaalpostcode",
               "pt": "o aeroporto de partida ou o código postal de recolha", "tr": "kalkış havalimanı veya alım posta kodu"},
    "destination": {"en": "the destination airport (or city)", "de": "den Zielflughafen (oder die Stadt)",
                    "fr": "l'aéroport de destination (ou la ville)", "es": "el aeropuerto de destino (o la ciudad)",
                    "it": "l'aeroporto di destinazione (o la città)", "nl": "de luchthaven van bestemming (of de stad)",
                    "pt": "o aeroporto de destino (ou a cidade)", "tr": "varış havalimanı (veya şehir)"},
    "weight": {"en": "total gross weight in kg", "de": "das Bruttogewicht gesamt in kg",
               "fr": "le poids brut total en kg", "es": "el peso bruto total en kg", "it": "il peso lordo totale in kg",
               "nl": "het totale brutogewicht in kg", "pt": "o peso bruto total em kg", "tr": "toplam brüt ağırlık (kg)"},
    "dimensions or volume": {"en": "number of pieces with their dimensions (or the volume in cbm)",
                             "de": "die Anzahl Packstücke mit Maßen (oder das Volumen in cbm)",
                             "fr": "le nombre de colis avec leurs dimensions (ou le volume en m³)",
                             "es": "el número de bultos con sus medidas (o el volumen en m³)",
                             "it": "il numero di colli con le misure (o il volume in m³)",
                             "nl": "het aantal colli met de afmetingen (of het volume in m³)",
                             "pt": "o número de volumes com as dimensões (ou o volume em m³)",
                             "tr": "parça sayısı ve ölçüleri ya da hacim (m³)"},
    "ready date": {"en": "the ready date if you have it already", "de": "das Ladebereit-Datum falls schon bekannt",
                   "fr": "la date de mise à disposition si vous l'avez déjà",
                   "es": "la fecha en que la carga está lista si ya la tiene",
                   "it": "la data di pronto merce se già nota", "nl": "de gereeddatum als u die al weet",
                   "pt": "a data em que a carga está pronta se já souber", "tr": "biliniyorsa yükün hazır olacağı tarih"},
}
OUTRO = {"en": "Once I have that I'll send you the price right away.",
         "de": "Sobald ich das habe, schicke ich Ihnen sofort den Preis.",
         "fr": "Dès que je l'ai je vous envoie le prix tout de suite.", "es": "En cuanto lo tenga le envío el precio.",
         "it": "Appena li ho le mando subito il prezzo.", "nl": "Zodra ik dat heb stuur ik u meteen de prijs.",
         "pt": "Assim que tiver isso envio-lhe o preço de imediato.", "tr": "Bunları alır almaz fiyatı hemen gönderiyorum."}


CODE = re.compile(r"\b[A-Z]{3}\b")


def askable(missing: list[str], rfq: dict | None = None, text: str = "") -> list[str] | None:
    """The fields to ask for, or None when `missing` holds anything the question can't fix or no core field.
    A missing destination while the mail names two or more other airports we know ("Lot A to JFK, Lot B to ORD") is not
    missing but several shipments: a person, never "which destination?"."""
    if not missing or any(m not in ASKABLE for m in missing) or not CORE & set(missing):
        return None
    if "destination" in missing:
        from airports import known
        named = set(CODE.findall(text or "")) & known()
        named -= {(rfq or {}).get("origin"), (rfq or {}).get("destination")}
        if len(named) >= 2:
            return None
    return [f for f in ASKABLE if f in missing]


def fields_to_ask(missing: list[str], rfq: dict) -> list[str]:
    """`missing` plus the dims/volume with a missing weight (we ask anyway: one question, the chargeable weight) and
    the ready date when the mail has none."""
    fields = list(missing)
    if "weight" in fields and "dimensions or volume" not in fields and not rfq.get("volume_m3") and not all(
            p.get("length_cm") and p.get("width_cm") and p.get("height_cm") for p in rfq.get("pieces") or [{}]):
        fields.append("dimensions or volume")
    if not rfq.get("ready_date"):
        fields.append("ready date")
    return [f for f in (*ASKABLE, "ready date") if f in fields]


def question(lang: str, fields: list[str]) -> list[str]:
    """The lines of the question (without greeting and sign-off), in `lang` (else English)."""
    lang = lang if lang in INTRO else "en"
    names = [FIELDS[f][lang] for f in fields]
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} {AND[lang]} {names[-1]}"
    return [INTRO[lang].format(fields=listed) + "\n\n" + OUTRO[lang]]


# An answer with something to price in it: a figure with a unit, an airport code, a postcode, or a known field word.
# "Thanks, I'll check and come back to you" is no answer (R71): we keep waiting for the next mail.
ANSWER_SIGNAL = re.compile(r"(?i:\d[\d.,]*\s?(?:kg|kgs|kilos?|lbs?|t|tons?|cbm|m3|m³|pcs|pieces?|pallets?|boxes|cartons?|"
                           r"colli|cm|mm|in)\b)|\b[A-Z]{3}\b|\b\d{4,5}\b|"
                           r"\b(?i:to|nach|vers|à|a|naar|para|per|from|von|de|da|van)\s+[A-ZÀ-Ý][\w\-]{2,}")


def answers(text: str, asked: list[str] | tuple = ()) -> bool:
    """A bare answer counts too: "Chicago", "Landshut" (a city we know), "450" when we asked for the weight in kg.
    A reply that misses all of these waits silently, so a miss here costs the round."""
    text = text or ""
    if ANSWER_SIGNAL.search(text) or ("weight" in asked and re.search(r"\d", text)):
        return True
    from airports import CITY, _fold, known
    from extract import city_zone
    plain = _fold(text)
    return bool(city_zone(text)) or any(re.search(rf"(?<!\w){re.escape(_fold(c))}(?!\w)", plain)
                                        for c, code in CITY.items() if code in known())
