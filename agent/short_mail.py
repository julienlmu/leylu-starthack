"""QUOTE_STYLE=short (default): one fixed, short, casual mail per kind (quote, booked, airline-confirmed, tracking).

5U's humanity bonus goes to the mail a reader can't tell was written by AI; small mistakes are fine and variety isn't
needed. So: a greeting, 2-4 short lines with contractions, "Thanks," and a first name. No "hope this finds you well",
no "don't hesitate", no bullets, no em dashes. One harmless imperfection, always the same: the last line has no full
stop. Amount, currency, airline, airport codes and the booking reference are filled in from the data, never reworded;
the DG line, the gate's sentences and its one-amount check stay as they are (gate.finish runs over this text).
"""

from datetime import date

SIGN = {"en": "Thanks,\nLena", "de": "Danke und Grüße\nLena", "fr": "Merci,\nLena", "es": "Gracias,\nLena",
        "it": "Grazie,\nLena", "nl": "Groeten,\nLena", "pt": "Obrigada,\nLena", "tr": "Teşekkürler,\nLena"}
HI = {"en": "Hi", "de": "Hallo", "fr": "Bonjour", "es": "Hola", "it": "Ciao", "nl": "Hoi", "pt": "Olá", "tr": "Merhaba"}
# {carrier} {pieces} {kg} {origin} {destination} {amount}; pickup / transit / reply are added below
QUOTE = {
    "en": "{carrier} can fly your {goods} from {origin} to {destination} for {amount} all in{pickup}.{transit}",
    "de": "{carrier} kann Ihre {goods} von {origin} nach {destination} fliegen, für {amount} all-in{pickup}.{transit}",
    "fr": "{carrier} peut transporter vos {goods} de {origin} à {destination} pour {amount} tout compris{pickup}.{transit}",
    "es": "{carrier} puede llevar sus {goods} de {origin} a {destination} por {amount} todo incluido{pickup}.{transit}",
    "it": "{carrier} può portare i suoi {goods} da {origin} a {destination} per {amount} tutto incluso{pickup}.{transit}",
    "nl": "{carrier} kan uw {goods} van {origin} naar {destination} vliegen voor {amount} all-in{pickup}.{transit}",
    "pt": "A {carrier} pode levar os seus {goods} de {origin} para {destination} por {amount} tudo incluído{pickup}.{transit}",
    "tr": "{carrier}, {goods} gönderinizi {origin} çıkışlı {destination} varışlı {amount} her şey dahil taşıyabilir{pickup}.{transit}",
}
GOODS = {"en": ("{n} piece", "{n} pieces"), "de": ("{n} Packstück", "{n} Packstücke"), "fr": ("{n} colis", "{n} colis"),
         "es": ("{n} bulto", "{n} bultos"), "it": ("{n} collo", "{n} colli"), "nl": ("{n} colli", "{n} colli"),
         "pt": ("{n} volume", "{n} volumes"), "tr": ("{n} parça", "{n} parça")}
PICKUP = {"en": ", pickup included", "de": ", Abholung inklusive", "fr": ", enlèvement inclus",
          "es": ", recogida incluida", "it": ", ritiro incluso", "nl": ", ophalen inbegrepen",
          "pt": ", recolha incluída", "tr": ", alım dahil"}
TRANSIT = {"en": " It's about {n} in transit.", "de": " Laufzeit sind ca. {n}.", "fr": " Comptez environ {n}.",
           "es": " Son unos {n} de tránsito.", "it": " Sono circa {n} di transito.", "nl": " Het duurt ongeveer {n}.",
           "pt": " São cerca de {n} em trânsito.", "tr": " Yaklaşık {n} sürüyor."}
DAYS = {"en": ("{n} day", "{n} days"), "de": ("{n} Tag", "{n} Tage"), "fr": ("{n} jour", "{n} jours"),
        "es": ("{n} día", "{n} días"), "it": ("{n} giorno", "{n} giorni"), "nl": ("{n} dag", "{n} dagen"),
        "pt": ("{n} dia", "{n} dias"), "tr": ("{n} gün", "{n} gün")}
# the fixed imperfection: no full stop at the end
REPLY = {"en": "Space gets confirmed when I book, just reply yes and I'll book it",
         "de": "Der Platz wird bei der Buchung bestätigt, ein kurzes Ja reicht und ich buche",
         "fr": "La place est confirmée à la réservation, un simple oui et je réserve",
         "es": "El espacio se confirma al reservar, con un sí lo reservo",
         "it": "Lo spazio si conferma alla prenotazione, basta un sì e prenoto",
         "nl": "De ruimte wordt bij het boeken bevestigd, een kort ja is genoeg en ik boek",
         "pt": "O espaço é confirmado na reserva, basta um sim e eu reservo",
         "tr": "Yer rezervasyonda onaylanıyor, kısa bir evet yeterli, hemen ayarlarım"}
BOOKED = {
    "en": "All booked with {airline}, {origin} to {destination}, booking ref {ref}. I'll let you know once they confirm",
    "de": "Ist gebucht bei {airline}, {origin} nach {destination}, Buchungsnummer {ref}. Ich melde mich, sobald sie bestätigen",
    "fr": "C'est réservé avec {airline}, {origin} vers {destination}, référence {ref}. Je vous préviens dès qu'ils confirment",
    "es": "Reservado con {airline}, {origin} a {destination}, referencia {ref}. Le aviso en cuanto confirmen",
    "it": "Prenotato con {airline}, da {origin} a {destination}, riferimento {ref}. Le scrivo appena confermano",
    "nl": "Geboekt bij {airline}, {origin} naar {destination}, boekingsnummer {ref}. Ik laat het weten zodra ze bevestigen",
    "pt": "Reservado com a {airline}, {origin} para {destination}, referência {ref}. Aviso assim que confirmarem",
    "tr": "{airline} ile {origin}-{destination} rezervasyonu tamam, referans {ref}. Onaylayınca haber veririm",
}
CONFIRMED = {
    "en": "{airline} just confirmed {ref}, so you're all set. Ask me anytime for the status",
    "de": "{airline} hat {ref} gerade bestätigt, alles startklar. Fragen Sie jederzeit nach dem Status",
    "fr": "{airline} vient de confirmer {ref}, tout est prêt. Demandez-moi le statut quand vous voulez",
    "es": "{airline} acaba de confirmar {ref}, todo listo. Pregúnteme el estado cuando quiera",
    "it": "{airline} ha appena confermato {ref}, è tutto pronto. Mi chieda pure lo stato quando vuole",
    "nl": "{airline} heeft {ref} net bevestigd, alles staat klaar. Vraag gerust naar de status",
    "pt": "A {airline} acabou de confirmar {ref}, está tudo pronto. Pergunte-me o estado quando quiser",
    "tr": "{airline} {ref} rezervasyonunu onayladı, her şey hazır. Durumu istediğiniz zaman sorabilirsiniz",
}


def _lang(rfq: dict | None) -> str:
    code = ((rfq or {}).get("language") or "en").lower()[:2]
    return code if code in QUOTE else "en"


def _hi(lang: str, name: str | None) -> str:
    first = (name or "").split()[:1]
    return f"{HI[lang]} {first[0]}," if first else f"{HI[lang]},"


def _n(forms: tuple[str, str], n: int) -> str:
    return forms[0 if n == 1 else 1].format(n=n)


def _mail(lang: str, name: str | None, *lines: str) -> str:
    return f"{_hi(lang, name)}\n\n" + "\n".join(line for line in lines if line) + f"\n\n{SIGN[lang]}"


def quote(rfq: dict, option: dict, amount: str, dg_line: str | None) -> str:
    """The quote: one line with airline, route, the one amount; transit; the DG line if DG; the reply line."""
    lang = _lang(rfq)
    count = sum(int(p.get("count") or 1) for p in rfq.get("pieces") or []) or 1
    goods = _n(GOODS[lang], count)
    kg = sum(int(p.get("count") or 1) * (p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
    if kg >= 1:
        goods += f" ({round(kg):,} kg)"
    days = option.get("transit_days")
    transit = TRANSIT[lang].format(n=_n(DAYS[lang], max(1, round(days)))) if days else ""
    first = QUOTE[lang].format(carrier=option["carrier"], goods=goods, origin=rfq["origin"],
                               destination=rfq["destination"], amount=amount,
                               pickup=PICKUP[lang] if option.get("pickup") or rfq.get("pickup") else "",
                               transit=transit)
    return _mail(lang, rfq.get("contact_name"), first, dg_line, REPLY[lang])


def booked(rfq: dict, booking: dict) -> str:
    lang = _lang(rfq)
    return _mail(lang, rfq.get("contact_name"), BOOKED[lang].format(
        airline=booking["airline"], origin=rfq["origin"], destination=rfq["destination"],
        ref=booking["booking_reference"]))


def confirmed(session: dict) -> str:
    rfq, booking = session.get("rfq") or {}, session["booking"]
    lang = _lang(rfq)
    return _mail(lang, rfq.get("contact_name"), CONFIRMED[lang].format(airline=booking["airline"],
                                                                      ref=booking["booking_reference"]))


def tracking(session: dict) -> str:
    """English (tracking@ questions): where the booking stands, the latest airline update, then a short close."""
    booking, rfq = session["booking"], session.get("rfq") or {}
    status = ("booked and confirmed by the airline, ready to go" if booking.get("status") == "confirmed"
              else "booked, we're still waiting on the airline's confirmation")
    lines = [f"{booking['booking_reference']} ({rfq.get('origin')} to {rfq.get('destination')} with "
             f"{booking.get('airline')}) is {status}."]
    ready, pickup = rfq.get("ready_date"), (rfq.get("pickup") or {}).get("address")
    if updates := session.get("status_updates") or []:
        lines.append(f"Latest from them: {updates[-1]['text'].rstrip('.')}.")
    elif ready and str(ready) >= date.today().isoformat():  # only before the ready date: after it, may be wrong
        lines.append(f"It hasn't left yet, {'pickup from ' + pickup if pickup else 'handover at the airport'} "
                     f"is planned for {ready}.")
    if days := (session.get("quote") or {}).get("transit_days"):
        lines[-1] += f" Transit's about {_n(DAYS['en'], max(1, round(days)))}."
    lines.append("I'll keep you posted")
    return _mail("en", rfq.get("contact_name"), *lines)
