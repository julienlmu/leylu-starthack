"""Mail templates. Written by hand, not by the LLM (cost), and meant to read like a person wrote them (jury +10, criterion 4).

- Customer mails follow the RFQ's language (`rfq["language"]`, ISO 639-1); unknown languages fall back to English.
- The amount is always written as "EUR 1,856.00" in every language, so the scorer reads exactly one unambiguous number.
- Transit is written as whole days or hours, never with decimals, so it can't be mistaken for a price.
- Wording varies per request (stable per seed, so tests stay deterministic) so a run of quotes doesn't read like a form letter.
- Carrier bid requests and tracking answers stay in English: 5U's carrier and tracking agents write English,
  and bids.parse_bid relies on the reply format the bid request asks for.
"""
import re
from datetime import date
import zlib

SIGNER = "Lena"
TEAM = "Leylü Air Freight"  # our forwarder (5U is the organiser)

T = {
    "en": {
        "hi": "Hi,",
        "thanks": ["Thanks for your request{ref}.", "Thanks for sending this over{ref}."],
        "offer": "The {ask} for your {pieces} from {origin} to {destination} is a flight with {carrier}{transit}.{pickup}",
        "pieces": ("{n} piece", "{n} pieces"),
        "goods": " of {}",
        "pickup": " Pickup at your address is included.",
        "ask": {"cheapest": "cheapest option", "fastest": "fastest option", "best": "best mix of price and speed"},
        "transit": ", about {} in transit",
        "days": ("{n} day", "{n} days"),
        "hours": ("{n} hour", "{n} hours"),
        "price": "All-in price: {amount}",
        "dg": "Your packing list declares these goods as dangerous goods, so they fly as DG cargo: please send us the Shipper's Declaration for Dangerous Goods and the safety data sheet (MSDS) before pickup.",
        "cta": ["Just reply to this email and I'll book it for you right away.",
                "If that works for you, just reply and I'll take care of the booking."],
        "bye": "Best regards,",
        "booked": "It's booked: your shipment from {origin} to {destination} flies with {airline}, "
                  "booking reference {ref}.\n\nI'll let you know as soon as the airline confirms, "
                  "and you can ask me about the status any time.",
        "confirmed": "{airline} has confirmed booking {ref}, so your shipment is all set.",
    },
    "de": {
        "hi": "Hallo,",
        "thanks": ["vielen Dank für Ihre Anfrage{ref}.", "danke für Ihre Anfrage{ref}."],
        "offer": "Für Ihre Sendung ({pieces}) von {origin} nach {destination} ist die {ask} ein Flug "
                 "mit {carrier}{transit}.{pickup}",
        "pieces": ("{n} Packstück", "{n} Packstücke"),
        "goods": ", {}",
        "pickup": " Die Abholung bei Ihnen ist inklusive.",
        "ask": {"cheapest": "günstigste Option", "fastest": "schnellste Option",
                "best": "beste Mischung aus Preis und Laufzeit"},
        "transit": ", Laufzeit etwa {}",
        "days": ("{n} Tag", "{n} Tage"),
        "hours": ("{n} Stunde", "{n} Stunden"),
        "price": "All-in-Preis: {amount}",
        "dg": "Laut Ihrer Packliste handelt es sich um Gefahrgut, daher fliegt die Sendung als DG-Fracht: Bitte senden Sie uns vor der Abholung die Shipper's Declaration for Dangerous Goods und das Sicherheitsdatenblatt (MSDS).",
        "cta": ["Antworten Sie einfach auf diese Mail, dann buche ich sofort für Sie.",
                "Wenn das für Sie passt, antworten Sie einfach kurz und ich kümmere mich um die Buchung."],
        "bye": "Viele Grüße",
        "booked": "Ist gebucht: Ihre Sendung von {origin} nach {destination} fliegt mit {airline}, "
                  "Buchungsreferenz {ref}.\n\nSobald die Airline bestätigt, melde ich mich. "
                  "Fragen Sie gern jederzeit nach dem Status.",
        "confirmed": "{airline} hat die Buchung {ref} bestätigt, Ihre Sendung ist startklar.",
    },
    "fr": {
        "hi": "Bonjour,",
        "thanks": ["Merci pour votre demande{ref}.", "Merci de nous avoir contactés{ref}."],
        "offer": "Pour votre envoi ({pieces}) de {origin} à {destination}{pickup}, l'option {ask} est un vol "
                 "avec {carrier}{transit}.",
        "pieces": ("{n} colis", "{n} colis"),
        "goods": ", {}",
        "pickup": " avec enlèvement à votre adresse",
        "ask": {"cheapest": "la moins chère", "fastest": "la plus rapide", "best": "la plus adaptée"},
        "transit": ", environ {} de transit",
        "days": ("{n} jour", "{n} jours"),
        "hours": ("{n} heure", "{n} heures"),
        "price": "Prix tout compris : {amount}",
        "dg": "Votre liste de colisage déclare des marchandises dangereuses, l'envoi voyage donc en fret DG : merci de nous envoyer la Shipper's Declaration for Dangerous Goods et la fiche de données de sécurité (FDS/MSDS) avant l'enlèvement.",
        "cta": ["Répondez simplement à cet e-mail et je fais la réservation tout de suite.",
                "Si cela vous convient, un simple retour suffit et je m'occupe de la réservation."],
        "bye": "Bien cordialement,",
        "booked": "C'est réservé : votre envoi de {origin} à {destination} part avec {airline}, "
                  "référence de réservation {ref}.\n\nJe vous préviens dès que la compagnie confirme, "
                  "et vous pouvez me demander le statut à tout moment.",
        "confirmed": "{airline} a confirmé la réservation {ref}, votre envoi est prêt à partir.",
    },
    "es": {
        "hi": "Hola,",
        "thanks": ["Gracias por su solicitud{ref}.", "Muchas gracias por contactarnos{ref}."],
        "offer": "Para su envío ({pieces}) de {origin} a {destination}{pickup}, la opción {ask} es un vuelo "
                 "con {carrier}{transit}.",
        "pieces": ("{n} bulto", "{n} bultos"),
        "goods": ", {}",
        "pickup": " con recogida en su dirección",
        "ask": {"cheapest": "más económica", "fastest": "más rápida", "best": "más adecuada"},
        "transit": ", con unos {} de tránsito",
        "days": ("{n} día", "{n} días"),
        "hours": ("{n} hora", "{n} horas"),
        "price": "Precio todo incluido: {amount}",
        "dg": "Su lista de empaque declara mercancías peligrosas, por lo que el envío viaja como carga DG: envíenos por favor la Shipper's Declaration for Dangerous Goods y la hoja de datos de seguridad (MSDS) antes de la recogida.",
        "cta": ["Responda a este correo y lo reservo enseguida.",
                "Si le parece bien, solo responda y me encargo de la reserva."],
        "bye": "Saludos cordiales,",
        "booked": "Ya está reservado: su envío de {origin} a {destination} vuela con {airline}, "
                  "referencia de reserva {ref}.\n\nLe aviso en cuanto la aerolínea lo confirme, "
                  "y puede preguntarme por el estado cuando quiera.",
        "confirmed": "{airline} ha confirmado la reserva {ref}, su envío está listo.",
    },
    "it": {
        "hi": "Buongiorno,",
        "thanks": ["grazie per la sua richiesta{ref}.", "grazie per averci contattato{ref}."],
        "offer": "Per la sua spedizione ({pieces}) da {origin} a {destination}{pickup}, l'opzione {ask} è un volo "
                 "con {carrier}{transit}.",
        "pieces": ("{n} collo", "{n} colli"),
        "goods": ", {}",
        "pickup": " con ritiro al suo indirizzo",
        "ask": {"cheapest": "più economica", "fastest": "più veloce", "best": "migliore"},
        "transit": ", circa {} di transito",
        "days": ("{n} giorno", "{n} giorni"),
        "hours": ("{n} ora", "{n} ore"),
        "price": "Prezzo tutto incluso: {amount}",
        "dg": "La sua packing list dichiara merci pericolose, quindi la spedizione viaggia come merce DG: ci invii per favore la Shipper's Declaration for Dangerous Goods e la scheda di sicurezza (MSDS) prima del ritiro.",
        "cta": ["Mi risponda pure a questa e-mail e prenoto subito.",
                "Se le va bene, basta una risposta e penso io alla prenotazione."],
        "bye": "Cordiali saluti,",
        "booked": "Ho prenotato: la sua spedizione da {origin} a {destination} vola con {airline}, "
                  "riferimento di prenotazione {ref}.\n\nLe scrivo appena la compagnia conferma, "
                  "e può chiedermi lo stato in qualsiasi momento.",
        "confirmed": "{airline} ha confermato la prenotazione {ref}, la spedizione è pronta a partire.",
    },
    "nl": {
        "hi": "Hallo,",
        "thanks": ["Bedankt voor uw aanvraag{ref}.", "Dank u wel voor uw aanvraag{ref}."],
        "offer": "Voor uw zending ({pieces}) van {origin} naar {destination}{pickup} is de {ask} optie een vlucht "
                 "met {carrier}{transit}.",
        "pieces": ("{n} collo", "{n} colli"),
        "goods": ", {}",
        "pickup": " inclusief ophalen op uw adres",
        "ask": {"cheapest": "goedkoopste", "fastest": "snelste", "best": "beste"},
        "transit": ", met ongeveer {} transittijd",
        "days": ("{n} dag", "{n} dagen"),
        "hours": ("{n} uur", "{n} uur"),
        "price": "All-in prijs: {amount}",
        "dg": "Volgens uw paklijst gaat het om gevaarlijke stoffen, dus de zending vliegt als DG-vracht: stuur ons vóór het ophalen de Shipper's Declaration for Dangerous Goods en het veiligheidsinformatieblad (MSDS).",
        "cta": ["Antwoord gewoon op deze e-mail, dan boek ik het meteen voor u.",
                "Als dat goed is, stuur dan even een reactie en ik regel de boeking."],
        "bye": "Met vriendelijke groet,",
        "booked": "Het is geboekt: uw zending van {origin} naar {destination} vliegt met {airline}, "
                  "boekingsreferentie {ref}.\n\nIk laat het u weten zodra de airline bevestigt, "
                  "en u kunt altijd naar de status vragen.",
        "confirmed": "{airline} heeft boeking {ref} bevestigd, uw zending staat klaar.",
    },
    "pt": {
        "hi": "Olá,",
        "thanks": ["Agradecemos o seu pedido{ref}."],
        "offer": "Para o seu envio ({pieces}) de {origin} para {destination}{pickup}, a opção {ask} é um voo "
                 "com {carrier}{transit}.",
        "pieces": ("{n} volume", "{n} volumes"),
        "goods": ", {}",
        "pickup": " com recolha na sua morada",
        "ask": {"cheapest": "mais barata", "fastest": "mais rápida", "best": "mais adequada"},
        "transit": ", com cerca de {} de trânsito",
        "days": ("{n} dia", "{n} dias"),
        "hours": ("{n} hora", "{n} horas"),
        "price": "Preço com tudo incluído: {amount}",
        "dg": "A sua lista de embalagem declara mercadorias perigosas, por isso o envio segue como carga DG: envie-nos a Shipper's Declaration for Dangerous Goods e a ficha de dados de segurança (MSDS) antes da recolha.",
        "cta": ["Basta responder a este e-mail e faço a reserva de imediato."],
        "bye": "Com os melhores cumprimentos,",
        "booked": "Está reservado: o seu envio de {origin} para {destination} segue com {airline}, "
                  "referência de reserva {ref}.\n\nAviso assim que a companhia aérea confirmar, "
                  "e pode perguntar pelo estado a qualquer momento.",
        "confirmed": "A {airline} confirmou a reserva {ref}, o seu envio está pronto.",
    },
    "tr": {
        "hi": "Merhaba,",
        "thanks": ["Talebiniz{ref} için teşekkür ederiz."],
        "offer": "{origin}-{destination} gönderiniz ({pieces}{pickup}) için {ask} seçeneğimiz "
                 "{carrier} ile uçuş{transit}.",
        "pieces": ("{n} parça", "{n} parça"),
        "goods": ", {}",
        "pickup": ", adresinizden alım dahil",
        "ask": {"cheapest": "en uygun fiyatlı", "fastest": "en hızlı", "best": "en uygun"},
        "transit": ", transit süresi yaklaşık {}",
        "days": ("{n} gün", "{n} gün"),
        "hours": ("{n} saat", "{n} saat"),
        "price": "Her şey dahil fiyat: {amount}",
        "dg": "Paketleme listenize göre bu gönderi tehlikeli madde içeriyor ve DG kargo olarak uçacak: lütfen alımdan önce Shipper's Declaration for Dangerous Goods belgesini ve güvenlik bilgi formunu (MSDS) bize gönderin.",
        "cta": ["Bu e-postayı yanıtlamanız yeterli, rezervasyonu hemen yapayım."],
        "bye": "Saygılarımla,",
        "booked": "Rezervasyonu yaptım: {origin}-{destination} gönderiniz {airline} ile uçuyor, "
                  "rezervasyon referansı {ref}.\n\nHavayolu onaylar onaylamaz size haber vereceğim; "
                  "durumu istediğiniz zaman sorabilirsiniz.",
        "confirmed": "{airline} {ref} rezervasyonunu onayladı, gönderiniz hazır.",
    },
}


def _t(rfq: dict | None) -> dict:
    code = ((rfq or {}).get("language") or "en").lower()[:2]
    return T.get(code, T["en"])


def _pick(options: list[str], seed: str) -> str:
    return options[zlib.crc32(seed.encode()) % len(options)]


def _plural(forms: tuple[str, str], n: int) -> str:
    return forms[0 if n == 1 else 1].format(n=n)


def _duration(t: dict, days: float) -> str:
    if days < 1.5:
        return _plural(t["hours"], max(1, round(days * 24)))
    return _plural(t["days"], round(days))


def _transit(t: dict, days: float | None) -> str:
    return t["transit"].format(_duration(t, days)) if days else ""


def _amount(option: dict) -> str:
    return f"{option['currency']} {option['total']:,.2f}"


def _sign(t: dict) -> str:
    return f"{t['bye']}\n{SIGNER}\n{TEAM}"


def _mail(t: dict, *paragraphs: str, name: str | None = None) -> str:
    return "\n\n".join([_hi(t, name), *paragraphs, _sign(t)])


def _hi(t: dict, name: str | None) -> str:
    """ "Hi Anna," when we know the customer's first name, else the plain "Hi,"."""
    first = (name or "").split()[:1]
    return f"{t['hi'].rstrip(',')} {first[0]}," if first else t["hi"]


CLOSINGS = re.compile(r"\b(?:regards|greetings|gr(?:ü|ue|u)(?:ß|ss)en?|gru(?:ß|ss)|cheers|thanks|thank you|danke|dank|"
                      r"saludos?|cordialement|salutations|merci|cumprimentos|obrigad[oa]|saluti|grazie|groeten|"
                      r"selamlar|saygılar(?:ımla)?|teşekkürler|best|mfg)\b", re.I)
TITLES = {"dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.", "herr", "frau", "prof", "prof."}
# A signature line with one of these is a company or a team, not a person: greet with the plain "Hi,".
NOT_A_NAME = {"gmbh", "ag", "ab", "ltd", "inc", "llc", "kg", "co", "se", "sa", "srl", "spa", "bv", "oy", "team", "the",
              "group", "logistics", "logistik", "shipping", "purchasing", "einkauf", "versand", "department", "abteilung"}


def signature_name(body: str) -> str | None:
    """The sender's name from the line after the last closing ("Kind regards" / "Viele Gruesse"), e.g. "Anna Sonnberg".

    A greeting with the wrong name is worse than a plain "Hi,", so anything unsure returns None:
    a company line ("ACME Logistics"), an all-caps word ("ACME").
    """
    lines = [line.strip() for line in (body or "").splitlines()]
    for i in range(len(lines) - 1, -1, -1):  # the last closing is the signature; "Thank you in advance." is not
        line = lines[i]
        if not (line and len(line) < 60 and CLOSINGS.search(line)):
            continue
        following = next((l for l in lines[i + 1:] if l), "")
        if CLOSINGS.search(following):
            continue  # the real closing is the next line; the loop reaches it
        following = re.split(r"\s*[|,]\s*", following)[0]  # "Anna Sonnberg, Head of Logistics"
        words = [w for w in following.split() if w.lower() not in TITLES]
        if 1 <= len(words) <= 4 and all(w[:1].isupper() and re.sub(r"[-.']", "", w).isalpha() for w in words):
            if any(w.lower().strip(".") in NOT_A_NAME for w in words) or (len(words[0]) > 1 and words[0].isupper()):
                return None
            return " ".join(words)
    return None


def _pieces(rfq: dict) -> str:
    lines = []
    for p in rfq["pieces"]:
        dims = f"{p['length_cm']:g} x {p['width_cm']:g} x {p['height_cm']:g} cm, " if p["length_cm"] else ""
        lines.append(f"{p['count']} pcs, {dims}{p['weight_kg']:g} kg each")
    if rfq.get("volume_m3"):
        lines.append(f"total volume {rfq['volume_m3']:g} m³")
    return "; ".join(lines)


def bid_request_text(rfq: dict, kind: str) -> str:
    """Bid request to an airline or trucker. The answer format we ask for lets bids.parse_bid read it for free."""
    if kind == "trucker":
        service = f"pickup from {rfq['pickup']['address']} to {rfq['origin']} airport"
        postcode = _pickup_postcode(rfq)
        if postcode and postcode not in (rfq["pickup"].get("address") or ""):
            service += f" (pickup postcode {postcode})"  # truckers ask for it otherwise (round 15)
    else:
        service = f"air freight {rfq['origin']} to {rfq['destination']}"
    goods = rfq["commodity"] or "general cargo"
    dg = "dangerous goods" if rfq["dangerous_goods"] else "no dangerous goods"
    return (
        f"Hi,\n\n"
        f"we have a new shipment and would love your best offer:\n\n"
        f"Service: {service}\n"
        f"Ready: {rfq['ready_date'] or 'now'}\n"
        f"Pieces: {_pieces(rfq)}\n"
        f"Goods: {goods}, {dg}\n\n"
        f"Could you reply with your all-in price, transit time and rate ID in this format?\n"
        f"Total: 1234.00 EUR\nTransit: 2 days\nRate ID: ABC123\n\n"
        f"Thanks a lot!\n{SIGNER}\n{TEAM}"
    )


def quote_text(rfq: dict, option: dict) -> str:
    # The mail states exactly one amount, the all-in total: a breakdown would add more numbers for the scorer to misread.
    t = _t(rfq)
    seed = rfq.get("customer_reference") or f"{rfq['origin']}{rfq['destination']}"
    ref = f" ({rfq['customer_reference']})" if rfq.get("customer_reference") else ""
    pieces = _plural(t["pieces"], sum(p["count"] for p in rfq["pieces"]))
    goods = (rfq.get("commodity") or "").strip()
    if goods and len(goods) <= 60 and not re.search(r"\d", goods):  # one amount per mail: no digits from the goods line
        pieces += t["goods"].format(goods)  # "3 pieces of machine parts" / "(3 Packstücke, Maschinenteile)"
    offer = t["offer"].format(
        pieces=pieces,
        origin=rfq["origin"], destination=rfq["destination"],
        pickup=t["pickup"] if rfq.get("pickup") else "",
        ask=t["ask"].get(rfq.get("ask"), t["ask"]["best"]),
        carrier=option["carrier"], transit=_transit(t, option.get("transit_days")),
    )
    dg = [t["dg"]] if rfq.get("dangerous_goods") else []  # 5U rejects DG quotes without the DG papers (dg_docs_missing)
    return _mail(t, f"{_pick(t['thanks'], seed).format(ref=ref)} {offer}", *dg,
                 t["price"].format(amount=_amount(option)), _pick(t["cta"], seed), name=rfq.get("contact_name"))


def booking_text(rfq: dict, booking: dict) -> str:
    t = _t(rfq)
    return _mail(t, t["booked"].format(origin=rfq["origin"], destination=rfq["destination"],
                                       airline=booking["airline"], ref=booking["booking_reference"]),
                 name=rfq.get("contact_name"))


def booking_confirmed_text(session: dict) -> str:
    t, booking = _t(session.get("rfq")), session["booking"]
    return _mail(t, t["confirmed"].format(airline=booking["airline"], ref=booking["booking_reference"]),
                 name=(session.get("rfq") or {}).get("contact_name"))


def tracking_text(session: dict) -> str:
    t = T["en"]
    booking, rfq, quote = session["booking"], session["rfq"], session.get("quote") or {}
    if booking.get("status") == "confirmed":
        status = "booked and confirmed by the airline, ready to ship"
    else:
        status = "booked, we're waiting for the airline's confirmation"
    updates = session.get("status_updates") or []
    latest = f"\n\nLatest update: {updates[-1]['text']}." if updates else ""
    ready = rfq.get("ready_date")
    pickup = (rfq.get("pickup") or {}).get("address")
    # Only before the ready date and without a newer airline update; after that "hasn't left yet" may be wrong.
    if ready and not updates and str(ready) >= date.today().isoformat():
        start = f"pickup from {pickup}" if pickup else "handover at the airport"
        latest += f"\n\nIt hasn't left yet: {start} is planned for {ready}, then it flies with {booking.get('airline') or 'the airline'}."
    days = quote.get("transit_days")
    planned = f"\nPlanned transit time: about {_duration(t, days)}." if days else ""
    return _mail(
        t,
        f"Here's where booking {booking['booking_reference']} stands ({rfq['origin']} to {rfq['destination']} "
        f"with {booking['airline']}): {status}.{latest}{planned}",
        "If anything else comes up, just let me know.",
        name=rfq.get("contact_name"),
    )


def tracking_unknown_text() -> str:
    t = T["en"]
    return _mail(
        t,
        "I couldn't find a booking with that reference on our side. Could you send me the booking reference "
        "(it starts with BK-)? Then I'll check right away.",
    )


def _pickup_postcode(rfq: dict) -> str | None:
    """The pickup postcode from the address, else the zone's digits padded (truckers rate by the 2-digit zone)."""
    pickup = rfq.get("pickup") or {}
    postcode = next(iter(re.findall(r"\b\d{5}\b", pickup.get("address") or "")), None)
    if not postcode and pickup.get("zone"):
        postcode = f"{pickup['zone']}000"  # exact address follows with the booking
    return postcode


def info_reply_text(rfq: dict, asks: list[str]) -> str:
    """Our answer when a carrier asks for details before quoting: everything we know about the shipment."""
    pickup = rfq.get("pickup") or {}
    address = pickup.get("address") or ""
    postcode = _pickup_postcode(rfq)
    lines = []
    if pickup:
        lines.append(f"Pickup postcode: {postcode or 'see address'}")
        lines.append(f"Pickup address: {address or 'customer site'}")
    lines.append(f"Departure airport: {rfq.get('origin')}")
    if rfq.get("destination"):
        lines.append(f"Destination airport: {rfq['destination']}")
    lines.append(f"Ready: {rfq.get('ready_date') or 'now'}")
    lines.append(f"Pieces: {_pieces(rfq)}")
    lines.append(f"Goods: {rfq.get('commodity') or 'general cargo'}, "
                 f"{'dangerous goods' if rfq.get('dangerous_goods') else 'no dangerous goods'}")
    return (f"Hi,\n\nthanks for getting back to us so quickly. Here are the details:\n\n" + "\n".join(lines) +
            f"\n\nCould you send us your all-in price in this format?\nTotal: 1234.00 EUR\nTransit: 1 day\n"
            f"Rate ID: ABC123\n\nThanks a lot!\n{SIGNER}\n{TEAM}")
