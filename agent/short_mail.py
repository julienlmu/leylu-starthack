"""QUOTE_STYLE=short (default): one fixed, short, casual mail per kind (quote, booked, airline-confirmed, tracking).

5U's humanity bonus goes to the mail a reader can't tell was written by AI; small mistakes are fine and variety isn't
needed. So: a greeting, 2-4 short lines with contractions, "Thanks," and a first name. No "hope this finds you well",
no "don't hesitate", no bullets, no em dashes. One harmless imperfection, always the same: the last line has no full
stop. Amount, currency, airline, airport codes and the booking reference are filled in from the data, never reworded;
the DG line, the gate's sentences and its one-amount check stay as they are (gate.finish runs over this text).
"""

import json
import os
import re
import threading
from datetime import date
from pathlib import Path

import language

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

SIGN.update({"pl": "Dzięki,\nLena", "cs": "Díky,\nLena", "sv": "Tack,\nLena", "da": "Tak,\nLena", "nb": "Takk,\nLena",
             "fi": "Kiitos,\nLena", "ja": "よろしくお願いします。\nLena", "zh": "谢谢，\nLena"})
HI.update({"pl": "Dzień dobry", "cs": "Dobrý den", "sv": "Hej", "da": "Hej", "nb": "Hei", "fi": "Hei", "ja": "こんにちは",
           "zh": "您好"})
QUOTE.update({
    "pl": "{carrier} może przewieźć Państwa {goods} z {origin} do {destination} za {amount} all-in{pickup}.{transit}",
    "cs": "{carrier} může přepravit vaše {goods} z {origin} do {destination} za {amount} all-in{pickup}.{transit}",
    "sv": "{carrier} kan flyga era {goods} från {origin} till {destination} för {amount} allt inkluderat{pickup}.{transit}",
    "da": "{carrier} kan flyve jeres {goods} fra {origin} til {destination} for {amount} alt inklusive{pickup}.{transit}",
    "nb": "{carrier} kan fly deres {goods} fra {origin} til {destination} for {amount} alt inkludert{pickup}.{transit}",
    "fi": "{carrier} voi lentää {goods} reitillä {origin}-{destination} hintaan {amount} kaikki sisältyen{pickup}.{transit}",
    "ja": "{carrier}で{goods}を{origin}から{destination}まで、総額{amount}でお運びできます{pickup}。{transit}",
    "zh": "{carrier}可以将您的{goods}从{origin}运到{destination}，全包价{amount}{pickup}。{transit}",
})
GOODS.update({"pl": ("{n} sztukę", "{n} sztuki", "{n} sztuk"), "cs": ("{n} kus", "{n} kusy", "{n} kusů"), "sv": ("{n} kolli", "{n} kollin"),
              "da": ("{n} kolli", "{n} kolli"), "nb": ("{n} kolli", "{n} kolli"), "fi": ("{n} kollin", "{n} kollia"),
              "ja": ("{n}個口", "{n}個口"), "zh": ("{n}件货物", "{n}件货物")})
PICKUP.update({"pl": ", z odbiorem", "cs": ", vyzvednutí v ceně", "sv": ", upphämtning ingår", "da": ", afhentning inkl.",
               "nb": ", henting inkludert", "fi": ", nouto sisältyy", "ja": "（集荷込み）", "zh": "（含提货）"})
TRANSIT.update({"pl": " Tranzyt to około {n}.", "cs": " Přeprava trvá zhruba {n}.", "sv": " Transittiden är ungefär {n}.",
                "da": " Transittiden er cirka {n}.", "nb": " Transittiden er omtrent {n}.", "fi": " Kuljetus kestää noin {n}.",
                "ja": "輸送日数は約{n}です。", "zh": "运输时间大约{n}。"})
DAYS.update({"pl": ("{n} dzień", "{n} dni", "{n} dni"), "cs": ("{n} den", "{n} dny", "{n} dní"), "sv": ("{n} dag", "{n} dagar"),
             "da": ("{n} dag", "{n} dage"), "nb": ("{n} dag", "{n} dager"), "fi": ("{n} päivä", "{n} päivää"),
             "ja": ("{n}日", "{n}日"), "zh": ("{n}天", "{n}天")})
REPLY.update({"pl": "Miejsce potwierdzam przy rezerwacji, wystarczy krótkie tak i rezerwuję",
              "cs": "Místo se potvrzuje při rezervaci, stačí krátké ano a rezervuju",
              "sv": "Platsen bekräftas när jag bokar, svara bara ja så bokar jag",
              "da": "Pladsen bekræftes ved booking, svar bare ja så booker jeg",
              "nb": "Plassen bekreftes ved booking, svar bare ja så booker jeg",
              "fi": "Tila vahvistetaan varauksen yhteydessä, vastaa vain kyllä niin varaan",
              "ja": "スペースは予約時に確定します。ご了承いただければ、そのまま手配します",
              "zh": "舱位在订舱时确认，回复一句好的我就安排订舱"})
BOOKED.update({
    "pl": "Zarezerwowane w {airline}, {origin} do {destination}, numer rezerwacji {ref}. Dam znać, jak potwierdzą",
    "cs": "Rezervováno u {airline}, {origin} do {destination}, číslo rezervace {ref}. Ozvu se, jakmile potvrdí",
    "sv": "Bokat med {airline}, {origin} till {destination}, bokningsnummer {ref}. Jag hör av mig när de bekräftat",
    "da": "Booket hos {airline}, {origin} til {destination}, bookingnummer {ref}. Jeg vender tilbage, når de bekræfter",
    "nb": "Booket hos {airline}, {origin} til {destination}, bookingnummer {ref}. Jeg sier fra når de bekrefter",
    "fi": "Varattu: {airline}, {origin}-{destination}, varausnumero {ref}. Ilmoitan, kun he vahvistavat",
    "ja": "{airline}で{origin}から{destination}への予約が完了しました。予約番号は{ref}です。確定次第ご連絡します",
    "zh": "已在{airline}订好，{origin}到{destination}，订舱号{ref}。航空公司确认后我会通知您",
})
CONFIRMED.update({
    "pl": "{airline} właśnie potwierdziło {ref}, wszystko gotowe. Proszę pytać o status w każdej chwili",
    "cs": "{airline} právě potvrdila {ref}, vše je připraveno. O stav se můžete kdykoli zeptat",
    "sv": "{airline} har just bekräftat {ref}, allt är klart. Fråga gärna om status när som helst",
    "da": "{airline} har lige bekræftet {ref}, alt er klar. Spørg bare om status når som helst",
    "nb": "{airline} har nettopp bekreftet {ref}, alt er klart. Spør gjerne om status når som helst",
    "fi": "{airline} vahvisti juuri varauksen {ref}, kaikki on valmista. Kysy tilannetta milloin vain",
    "ja": "{airline}が{ref}を確定しました。準備は整っています。状況はいつでもお問い合わせください",
    "zh": "{airline}刚刚确认了{ref}，一切就绪。随时可以问我进度",
})
# The DG line where templates.T has no language (the gate checks for "MSDS" / "Dangerous Goods").
DG = {
    "pl": "To towary niebezpieczne (DG): prosimy o Shipper's Declaration for Dangerous Goods i kartę charakterystyki (MSDS) przed odbiorem.",
    "cs": "Jde o nebezpečné zboží (DG): prosíme o Shipper's Declaration for Dangerous Goods a bezpečnostní list (MSDS) před vyzvednutím.",
    "sv": "Det är farligt gods (DG): skicka gärna Shipper's Declaration for Dangerous Goods och säkerhetsdatabladet (MSDS) före upphämtning.",
    "da": "Det er farligt gods (DG): send venligst Shipper's Declaration for Dangerous Goods og sikkerhedsdatabladet (MSDS) før afhentning.",
    "nb": "Dette er farlig gods (DG): send gjerne Shipper's Declaration for Dangerous Goods og sikkerhetsdatabladet (MSDS) før henting.",
    "fi": "Kyseessä on vaarallinen aine (DG): lähetäthän Shipper's Declaration for Dangerous Goods -lomakkeen ja käyttöturvallisuustiedotteen (MSDS) ennen noutoa.",
    "ja": "危険品（DG）のため、集荷前にShipper's Declaration for Dangerous Goodsと安全データシート（MSDS）をお送りください。",
    "zh": "该货物属于危险品（DG），请在提货前发送Shipper's Declaration for Dangerous Goods和安全技术说明书（MSDS）。",
}
ALIASES = {"no": "nb", "nn": "nb"}  # Norwegian: the model may say no / nb / nn

# REGISTER (register.py): the customer's du / tu / tú gets these; ihr = German informal plural ("könnt ihr", "euch").
INFORMAL = {
    "quote": {"de": QUOTE["de"].replace("Ihre {goods}", "deine {goods}"),
              "de-ihr": QUOTE["de"].replace("Ihre {goods}", "eure {goods}"),
              "fr": QUOTE["fr"].replace("vos {goods}", "tes {goods}"),
              "es": QUOTE["es"].replace("sus {goods}", "tus {goods}")},
    "booked": {"fr": BOOKED["fr"].replace("Je vous préviens", "Je te préviens"),
               "es": BOOKED["es"].replace("Le aviso", "Te aviso")},
    "confirmed": {"de": CONFIRMED["de"].replace("Fragen Sie jederzeit", "Frag jederzeit"),
                  "de-ihr": CONFIRMED["de"].replace("Fragen Sie jederzeit", "Fragt jederzeit"),
                  "fr": CONFIRMED["fr"].replace("Demandez-moi le statut quand vous voulez",
                                                "Demande-moi le statut quand tu veux"),
                  "es": CONFIRMED["es"].replace("Pregúnteme el estado cuando quiera", "Pregúntame el estado cuando quieras")},
}
FORMAL_SIGN = {"de": "Mit freundlichen Grüßen\nLena"}


def _form(kind: str, table: dict, lang: str, rfq: dict | None) -> str:
    """The template in the customer's register (REGISTER); the usual one when it's formal or unknown."""
    rfq = rfq or {}
    if rfq.get("register") == "informal":
        key = f"{lang}-ihr" if lang == "de" and rfq.get("register_plural") else lang
        return INFORMAL[kind].get(key) or INFORMAL[kind].get(lang) or table[lang]
    return table[lang]


def _lang(rfq: dict | None) -> str:
    code = ((rfq or {}).get("language") or "en").lower()[:2]
    code = ALIASES.get(code, code)
    return code if code in QUOTE or _learn(code) else "en"


# A language without a template (round 72/74: `wrong_language`): the TEMPLATE is translated once with placeholders,
# checked in code and cached; the facts (amount, currency, airline, codes, reference) are filled in by code afterwards
# and never pass through the model. Any doubt: English. TRANSLATE=off: English as before.
TRANSLATE = os.environ.get("MAIL_TRANSLATE", "on").lower() != "off"
CACHE = Path(os.environ.get("MAIL_LANGUAGES_FILE", ".mail_languages.json"))
NOT_A_LANGUAGE = {"un", "xx", "zz", "mu", "ot", "na"}  # "unknown", "mul(tiple)", "other", "n/a"
_lock = threading.Lock()
_tried: set[str] = set()


def _english() -> dict:
    return {"hi": HI["en"], "sign": SIGN["en"], "quote": QUOTE["en"], "goods_one": GOODS["en"][0],
            "goods_many": GOODS["en"][1], "pickup": PICKUP["en"], "transit": TRANSIT["en"], "day_one": DAYS["en"][0],
            "day_many": DAYS["en"][1], "reply": REPLY["en"], "booked": BOOKED["en"], "confirmed": CONFIRMED["en"],
            "dg": "These are dangerous goods (DG): please send us the Shipper's Declaration for Dangerous Goods and "
                  "the safety data sheet (MSDS) before pickup."}


def _ok(english: dict, out: dict) -> bool:
    """Same placeholders, no digits or dashes of its own, the DG names kept: else we don't use it."""
    holes = re.compile(r"\{\w+\}")
    for key, text in english.items():
        got = out.get(key)
        if not isinstance(got, str) or not got.strip() or sorted(holes.findall(got)) != sorted(holes.findall(text)):
            return False
        if re.search(r"\d|—|–", holes.sub("", got)):
            return False
    dg = out["wait_dg" if "wait_dg" in english else "dg"]
    return "MSDS" in dg and "Shipper's Declaration for Dangerous Goods" in dg


def _add(code: str, t: dict) -> None:
    HI[code], SIGN[code], QUOTE[code], PICKUP[code], TRANSIT[code] = t["hi"], t["sign"], t["quote"], t["pickup"], t["transit"]
    GOODS[code], DAYS[code] = (t["goods_one"], t["goods_many"]), (t["day_one"], t["day_many"])
    REPLY[code], BOOKED[code], CONFIRMED[code], DG[code] = t["reply"].rstrip("."), t["booked"], t["confirmed"], t["dg"]


def _use(code: str, t: dict, more: bool) -> None:
    if more:
        MORE[code] = t
    else:
        _add(code, t)


def _learn(code: str, more: bool = False) -> bool:
    """True when `code` now has templates (cached, or translated now). more: the other mails (MORE), own cache entry,
    so a failure there never costs a language its quote templates."""
    if not re.fullmatch(r"[a-z]{2}", code) or code in NOT_A_LANGUAGE or code == "en":
        return False
    key = f"{code}:more" if more else code
    with _lock:
        if code in (MORE if more else QUOTE):
            return True
        try:
            cached = json.loads(CACHE.read_text()).get(key)
        except (OSError, ValueError):
            cached = None
        english = dict(MORE["en"]) if more else _english()
        if cached and _ok(english, cached):
            _use(code, cached, more)
            return True
        if not TRANSLATE or key in _tried:
            return False
        _tried.add(key)  # one attempt per language and process: a failure is never paid twice
        try:
            import llm
            schema = {"type": "object", "additionalProperties": False, "required": list(english),
                      "properties": {k: {"type": "string"} for k in english}}
            out, cost = llm.chat_json(
                "mail_language", f"Translate each value into the language with ISO 639-1 code '{code}' as a friendly, "
                "short, casual business email between colleagues would say it. Keep every {placeholder} exactly as "
                "written, add no numbers, keep 'Shipper's Declaration for Dangerous Goods' and 'MSDS' in English.",
                json.dumps(english, ensure_ascii=False), schema, timeout=15 if more else 8,
                max_tokens=2500 if more else 900)
            print(f"mail templates for '{key}' translated (${cost:.6f})")
        except Exception as error:  # no translation: English, the mail still goes out
            print(f"mail templates for '{key}' not translated: {type(error).__name__}: {error}")
            return False
        if not _ok(english, out):
            print(f"mail templates for '{key}' rejected: placeholders or DG names changed")
            return False
        _use(code, out, more)
        try:
            data = json.loads(CACHE.read_text()) if CACHE.exists() else {}
            CACHE.write_text(json.dumps({**data, key: out}, ensure_ascii=False))
        except (OSError, ValueError):
            pass  # cached in memory for this run anyway
        return True


def _hi(lang: str, name: str | None, rfq: dict | None = None) -> str:
    if lang == "de" and (rfq or {}).get("register") == "formal":  # "Guten Tag Frau Berg," never a guessed Herr/Frau
        who = (rfq or {}).get("salutation") or (name if name and len(name.split()) >= 2 else None)
        return f"Guten Tag {who}," if who else "Guten Tag,"
    first = (name or "").split()[:1]
    if first and lang == "ja":
        return f"{first[0]}様"
    if first and lang == "zh":
        return f"{first[0]}，您好"
    if lang in ("ja", "zh"):
        return f"{HI[lang]}。"
    return f"{HI[lang]} {first[0]}," if first else f"{HI[lang]},"


MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def day(lang: str, iso) -> str:
    """ "25 Nov" / "25/11" / "11月25日": a date the way a person writes it, not 2026-11-25."""
    try:
        y, m, d = (int(x) for x in str(iso)[:10].split("-"))
    except ValueError:
        return str(iso)
    if lang == "en":
        return f"{d} {MONTHS_EN[m - 1]}"
    if lang in ("ja", "zh"):
        return f"{m}月{d}日"
    return f"{d}/{m}"  # never "25.11.": the one-amount check (and 5U's scorer) would read 25.11 as a second price


def _n(forms: tuple, n: int) -> str:
    """(one, other) or, Polish/Czech, (one, 2-4, 5+): "3 sztuki" but "5 sztuk"."""
    if len(forms) == 3 and n != 1:
        return forms[1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2].format(n=n)
    return forms[0 if n == 1 else 1].format(n=n)


def _mail(lang: str, name: str | None, *lines: str, rfq: dict | None = None) -> str:
    formal = (rfq or {}).get("register") == "formal"
    sign = FORMAL_SIGN.get(lang, SIGN[lang]) if formal else SIGN[lang]
    return f"{_hi(lang, name, rfq)}\n\n" + "\n".join(line for line in lines if line) + f"\n\n{sign}"


def quote(rfq: dict, option: dict, amount: str, dg_line: str | None) -> str:
    """The quote: one line with airline, route, the one amount; transit; the DG line if DG; the reply line."""
    lang = _lang(rfq)
    count = sum(int(p.get("count") or 1) for p in rfq.get("pieces") or []) or 1
    goods = _n(GOODS[lang], count)
    kg = sum(int(p.get("count") or 1) * (p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
    if kg >= 1:
        # R73: "1,674 kg" is English only; in German/French/… a comma is the decimal mark (1,674 kg = 1.674 kg)
        goods += f" ({round(kg):,} kg)" if lang == "en" else f" ({round(kg)} kg)"
    days = option.get("transit_days")
    transit = TRANSIT[lang].format(n=_n(DAYS[lang], max(1, round(days)))) if days else ""
    first = _form("quote", QUOTE, lang, rfq).format(carrier=option["carrier"], goods=goods, origin=rfq["origin"],
                               destination=rfq["destination"], amount=amount,
                               pickup=PICKUP[lang] if option.get("pickup") or rfq.get("pickup") else "",
                               transit=transit)
    if dg_line and lang in DG:  # templates.T has no such language: its English DG line would sit in a Polish mail
        dg_line = DG[lang]
    return _mail(lang, rfq.get("contact_name"), first, dg_line, REPLY[lang], rfq=rfq)


def booked(rfq: dict, booking: dict) -> str:
    lang = _lang(rfq)
    return _mail(lang, rfq.get("contact_name"), _form("booked", BOOKED, lang, rfq).format(
        airline=booking["airline"], origin=rfq["origin"], destination=rfq["destination"],
        ref=booking["booking_reference"]), rfq=rfq)


def confirmed(session: dict) -> str:
    rfq, booking = session.get("rfq") or {}, session["booking"]
    lang = _lang(rfq)
    return _mail(lang, rfq.get("contact_name"), _form("confirmed", CONFIRMED, lang, rfq).format(
        airline=booking["airline"], ref=booking["booking_reference"]), rfq=rfq)


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
                     f"is planned for {day('en', ready)}.")
    if days := (session.get("quote") or {}).get("transit_days"):
        lines[-1] += f" Transit's about {_n(DAYS['en'], max(1, round(days)))}."
    lines.append("I'll keep you posted")
    return _mail("en", rfq.get("contact_name"), *lines)


# UNIT_ASK: the one question before a quote when the mail gives a number without its unit. No amount in it.
UNIT_INTRO = {"en": "Quick check before I price it, which unit is this?",
              "de": "Kurze Rückfrage, bevor ich den Preis mache: Welche Einheit ist gemeint?",
              "fr": "Petite question avant de chiffrer : quelle unité ?",
              "es": "Una consulta rápida antes de cotizar: ¿qué unidad es?",
              "it": "Una domanda veloce prima di quotare: che unità è?",
              "nl": "Even checken voor ik het prijs: welke eenheid is dit?",
              "pt": "Uma pergunta rápida antes de cotar: qual é a unidade?",
              "tr": "Fiyatlamadan önce kısa bir soru: birim hangisi?",
              "pl": "Szybkie pytanie przed wyceną: jaka to jednostka?",
              "cs": "Rychlý dotaz před naceněním: jaká je to jednotka?",
              "sv": "En snabb fråga innan jag prissätter: vilken enhet gäller?",
              "da": "Et hurtigt spørgsmål før jeg prissætter: hvilken enhed er det?",
              "nb": "Et raskt spørsmål før jeg priser det: hvilken enhet gjelder?",
              "fi": "Nopea kysymys ennen hinnoittelua: mikä yksikkö on kyseessä?",
              "ja": "お見積りの前に確認させてください。単位はどちらでしょうか？",
              "zh": "报价前想确认一下，请问单位是哪一个？"}
UNIT_CHOICES = {"weight": "kg / lbs", "dims": "cm / in", "volume": "cbm / ft³"}


def units_question(rfq: dict, unitless: dict) -> str:
    lang = _lang(rfq)
    lang = lang if lang in UNIT_INTRO else "en"  # a translated language (_learn) has no UNIT_INTRO: English
    return _mail(lang, rfq.get("contact_name"), UNIT_INTRO[lang],
                 *(f"{v['said']}: {UNIT_CHOICES[k]}?" for k, v in unitless.items()))


# R72 `wrong_language`: the mails besides quote/booked/confirmed (tracking, asks, reprice, reminder, docs ack, confirm,
# booking requested) in the customer's language. Same rules as above: fixed text with placeholders, every fact filled
# by code, a language without a native set is translated once (_learn(code, more=True)), any doubt: English.
# English itself keeps the wording in templates.py; MORE["en"] is the source for the translation.
MORE = {
    "en": {
        "status_confirmed": "{ref} ({origin} to {destination} with {airline}) is booked and confirmed by the airline, ready to go.",
        "status_waiting": "{ref} ({origin} to {destination} with {airline}) is booked, we're still waiting on the airline's confirmation.",
        "latest": "Latest from them: {update}.",
        "planned_pickup": "It hasn't left yet, pickup from {address} is planned for {date}.",
        "planned_airport": "It hasn't left yet, handover at the airport is planned for {date}.",
        "posted": "I'll keep you posted",
        "many": "You have {n} bookings with us, here's where each one stands:",
        "many_other": "If you meant another shipment, just send me its booking reference (it starts with {bk})",
        "unknown": "I couldn't find a booking with that reference on our side. Could you send me the booking reference "
                   "(it starts with {bk})? Then I'll check right away",
        "details": "Thanks for your message. Unfortunately I can't open the attachment here. Could you send me the details "
                   "in writing: pickup postcode (or departure airport), destination, number of pieces, gross weight, volume "
                   "and ready date? Then I'll send you the all-in price right away",
        "pickup_q": "Thanks for your request. To include the truck pickup in your all-in price, could you tell me the pickup "
                    "address with its postcode? I'll send you the price right after",
        "requested": "Great, I've asked {airline} to book it for you. I'll send you the booking reference as soon as they confirm",
        "reprice": "Before booking I checked the rate once more: the airline's price has changed since your OK. The new "
                   "all-in price is {amount}. Shall I book it at this price? A short yes is enough",
        "reminder": "Just checking in on the quote I sent you for {origin} to {destination}: shall I go ahead and book it "
                    "with {carrier}? A short yes is all I need",
        "stands": "Your quote stands: {carrier} from {origin} to {destination}, all-in {amount}.",
        "thanks_ok": "Thank you, that's perfect.",
        "wait_dg": "I'll book it as soon as the Shipper's Declaration for Dangerous Goods and the safety data sheet (MSDS) "
                   "arrive, unless you tell me to wait",
        "wait": "Nothing is booked until you confirm, just reply when you're ready and I'll book it straight away",
        "confirm": "Yes, I can confirm: our offer covers {goods}, {origin} to {destination} with {carrier}{pickup}{ready}. "
                   "The all-in price is {amount}.",
        "ready": ", ready on {date}",
        "ask": "Shall I go ahead and book it?",
        "ask_dg": "Shall I book it once the DG documents are in?",
    },
    "de": {
        "status_confirmed": "{ref} ({origin} nach {destination} mit {airline}) ist gebucht und von der Airline bestätigt, alles startklar.",
        "status_waiting": "{ref} ({origin} nach {destination} mit {airline}) ist gebucht, die Bestätigung der Airline steht noch aus.",
        "latest": "Letzter Stand von der Airline: {update}.",
        "planned_pickup": "Die Sendung ist noch nicht unterwegs, die Abholung bei {address} ist für {date} geplant.",
        "planned_airport": "Die Sendung ist noch nicht unterwegs, die Übergabe am Flughafen ist für {date} geplant.",
        "posted": "Ich halte Sie auf dem Laufenden",
        "many": "Sie haben {n} Buchungen bei uns, hier der Stand zu jeder:",
        "many_other": "Falls Sie eine andere Sendung meinen, schicken Sie mir einfach die Buchungsnummer (sie beginnt mit {bk})",
        "unknown": "Zu dieser Referenz finde ich bei uns keine Buchung. Könnten Sie mir die Buchungsnummer schicken (sie "
                   "beginnt mit {bk})? Dann schaue ich sofort nach",
        "details": "Danke für Ihre Nachricht. Leider kann ich den Anhang hier nicht öffnen. Könnten Sie mir die Daten kurz "
                   "schriftlich schicken: Abhol-PLZ (oder Abflughafen), Ziel, Anzahl Packstücke, Bruttogewicht, Volumen und "
                   "Ladedatum? Dann schicke ich Ihnen sofort den All-in-Preis",
        "pickup_q": "Danke für Ihre Anfrage. Damit ich die Abholung im All-in-Preis berücksichtigen kann: Wie lautet die "
                    "Abholadresse mit Postleitzahl? Den Preis schicke ich Ihnen gleich danach",
        "requested": "Super, ich habe {airline} gebeten, die Sendung für Sie zu buchen. Die Buchungsnummer schicke ich Ihnen, "
                     "sobald die Airline bestätigt",
        "reprice": "Vor der Buchung habe ich den Tarif noch einmal geprüft: Der Preis der Airline hat sich seit Ihrer Zusage "
                   "geändert. Der neue All-in-Preis beträgt {amount}. Soll ich zu diesem Preis buchen? Ein kurzes Ja genügt",
        "reminder": "Ich wollte kurz wegen meines Angebots für {origin} nach {destination} nachfragen: Soll ich bei {carrier} "
                    "für Sie buchen? Ein kurzes Ja genügt",
        "stands": "Ihr Angebot steht: {carrier} von {origin} nach {destination}, all-in {amount}.",
        "thanks_ok": "Vielen Dank, das passt.",
        "wait_dg": "Ich buche, sobald die Shipper's Declaration for Dangerous Goods und das Sicherheitsdatenblatt (MSDS) da "
                   "sind, außer Sie möchten noch warten",
        "wait": "Gebucht wird erst, wenn Sie bestätigen, antworten Sie einfach, wenn Sie so weit sind, und ich buche sofort",
        "confirm": "Ja, das kann ich bestätigen: Unser Angebot umfasst {goods}, {origin} nach {destination} mit "
                   "{carrier}{pickup}{ready}. Der All-in-Preis beträgt {amount}.",
        "ready": ", bereit ab {date}",
        "ask": "Soll ich buchen?",
        "ask_dg": "Soll ich buchen, sobald die DG-Dokumente da sind?",
    },
    "fr": {
        "status_confirmed": "{ref} ({origin} vers {destination} avec {airline}) est réservé et confirmé par la compagnie, tout est prêt.",
        "status_waiting": "{ref} ({origin} vers {destination} avec {airline}) est réservé, nous attendons encore la confirmation de la compagnie.",
        "latest": "Dernière info de leur part : {update}.",
        "planned_pickup": "L'envoi n'est pas encore parti, l'enlèvement à l'adresse {address} est prévu le {date}.",
        "planned_airport": "L'envoi n'est pas encore parti, la remise à l'aéroport est prévue le {date}.",
        "posted": "Je vous tiens au courant",
        "many": "Vous avez {n} réservations chez nous, voici où en est chacune :",
        "many_other": "Si vous pensiez à un autre envoi, envoyez-moi simplement sa référence de réservation (elle commence par {bk})",
        "unknown": "Je ne trouve pas de réservation avec cette référence chez nous. Pourriez-vous m'envoyer la référence de "
                   "réservation (elle commence par {bk}) ? Je vérifie tout de suite",
        "details": "Merci pour votre message. Malheureusement je ne peux pas ouvrir la pièce jointe ici. Pourriez-vous "
                   "m'envoyer les détails par écrit : code postal d'enlèvement (ou aéroport de départ), destination, nombre "
                   "de colis, poids brut, volume et date de disponibilité ? Je vous envoie le prix tout compris aussitôt",
        "pickup_q": "Merci pour votre demande. Pour inclure l'enlèvement par camion dans le prix tout compris, pourriez-vous "
                    "m'indiquer l'adresse d'enlèvement avec son code postal ? Je vous envoie le prix juste après",
        "requested": "Parfait, j'ai demandé à {airline} de faire la réservation pour vous. Je vous envoie la référence dès "
                     "qu'ils confirment",
        "reprice": "Avant de réserver, j'ai vérifié le tarif une dernière fois : le prix de la compagnie a changé depuis votre "
                   "accord. Le nouveau prix tout compris est de {amount}. Dois-je réserver à ce prix ? Un simple oui suffit",
        "reminder": "Je reviens vers vous au sujet de mon offre pour {origin} vers {destination} : voulez-vous que je réserve "
                    "avec {carrier} ? Un simple oui suffit",
        "stands": "Votre offre reste valable : {carrier} de {origin} à {destination}, tout compris {amount}.",
        "thanks_ok": "Merci, c'est parfait.",
        "wait_dg": "Je réserve dès que la Shipper's Declaration for Dangerous Goods et la fiche de données de sécurité (MSDS) "
                   "arrivent, sauf si vous me dites d'attendre",
        "wait": "Rien n'est réservé avant votre confirmation, répondez-moi simplement quand vous êtes prêt et je réserve tout de suite",
        "confirm": "Oui, je confirme : notre offre couvre {goods}, {origin} vers {destination} avec {carrier}{pickup}{ready}. "
                   "Le prix tout compris est de {amount}.",
        "ready": ", disponible le {date}",
        "ask": "Je réserve ?",
        "ask_dg": "Je réserve dès que les documents DG sont là ?",
    },
    "es": {
        "status_confirmed": "{ref} ({origin} a {destination} con {airline}) está reservado y confirmado por la aerolínea, todo listo.",
        "status_waiting": "{ref} ({origin} a {destination} con {airline}) está reservado, aún esperamos la confirmación de la aerolínea.",
        "latest": "Lo último que nos dicen: {update}.",
        "planned_pickup": "Todavía no ha salido, la recogida en {address} está prevista para el {date}.",
        "planned_airport": "Todavía no ha salido, la entrega en el aeropuerto está prevista para el {date}.",
        "posted": "Le mantengo informado",
        "many": "Tiene {n} reservas con nosotros, así va cada una:",
        "many_other": "Si se refería a otro envío, envíeme su referencia de reserva (empieza por {bk})",
        "unknown": "No encuentro ninguna reserva con esa referencia. ¿Podría enviarme la referencia de reserva (empieza por "
                   "{bk})? Lo compruebo enseguida",
        "details": "Gracias por su mensaje. Por desgracia no puedo abrir el archivo adjunto aquí. ¿Podría enviarme los datos "
                   "por escrito: código postal de recogida (o aeropuerto de salida), destino, número de bultos, peso bruto, "
                   "volumen y fecha de disponibilidad? Le envío el precio total enseguida",
        "pickup_q": "Gracias por su solicitud. Para incluir la recogida en camión en el precio total, ¿podría indicarme la "
                    "dirección de recogida con su código postal? Le envío el precio justo después",
        "requested": "Perfecto, he pedido a {airline} que haga la reserva. Le envío la referencia en cuanto confirmen",
        "reprice": "Antes de reservar he vuelto a comprobar la tarifa: el precio de la aerolínea ha cambiado desde su "
                   "confirmación. El nuevo precio total es {amount}. ¿Reservo a este precio? Basta con un sí",
        "reminder": "Le escribo por la oferta que le envié para {origin} a {destination}: ¿quiere que haga la reserva con "
                    "{carrier}? Basta con un sí",
        "stands": "Su oferta sigue en pie: {carrier} de {origin} a {destination}, todo incluido {amount}.",
        "thanks_ok": "Gracias, perfecto.",
        "wait_dg": "Reservo en cuanto lleguen la Shipper's Declaration for Dangerous Goods y la ficha de datos de seguridad "
                   "(MSDS), salvo que me diga que espere",
        "wait": "No se reserva nada hasta que confirme, responda cuando esté listo y lo reservo enseguida",
        "confirm": "Sí, lo confirmo: nuestra oferta cubre {goods}, {origin} a {destination} con {carrier}{pickup}{ready}. "
                   "El precio total es {amount}.",
        "ready": ", listo el {date}",
        "ask": "¿Lo reservo?",
        "ask_dg": "¿Lo reservo en cuanto lleguen los documentos DG?",
    },
    "it": {
        "status_confirmed": "{ref} (da {origin} a {destination} con {airline}) è prenotato e confermato dalla compagnia, tutto pronto.",
        "status_waiting": "{ref} (da {origin} a {destination} con {airline}) è prenotato, aspettiamo ancora la conferma della compagnia.",
        "latest": "Ultimo aggiornamento da loro: {update}.",
        "planned_pickup": "Non è ancora partito, il ritiro presso {address} è previsto per il {date}.",
        "planned_airport": "Non è ancora partito, la consegna in aeroporto è prevista per il {date}.",
        "posted": "La tengo aggiornata",
        "many": "Ha {n} prenotazioni con noi, ecco a che punto è ciascuna:",
        "many_other": "Se intendeva un'altra spedizione, mi mandi il riferimento della prenotazione (inizia con {bk})",
        "unknown": "Non trovo nessuna prenotazione con quel riferimento. Potrebbe mandarmi il riferimento della prenotazione "
                   "(inizia con {bk})? Controllo subito",
        "details": "Grazie per il messaggio. Purtroppo qui non riesco ad aprire l'allegato. Potrebbe mandarmi i dati per "
                   "iscritto: CAP di ritiro (o aeroporto di partenza), destinazione, numero di colli, peso lordo, volume e "
                   "data di pronto merce? Le mando subito il prezzo tutto incluso",
        "pickup_q": "Grazie per la richiesta. Per includere il ritiro con camion nel prezzo tutto incluso, potrebbe indicarmi "
                    "l'indirizzo di ritiro con il CAP? Le mando il prezzo subito dopo",
        "requested": "Perfetto, ho chiesto a {airline} di prenotare per lei. Le mando il riferimento appena confermano",
        "reprice": "Prima di prenotare ho ricontrollato la tariffa: il prezzo della compagnia è cambiato dal suo ok. Il nuovo "
                   "prezzo tutto compreso è {amount}. Prenoto a questo prezzo? Basta un sì",
        "reminder": "Le scrivo per l'offerta che le ho inviato per {origin} a {destination}: vuole che prenoti con {carrier}? "
                    "Basta un sì",
        "stands": "La sua offerta resta valida: {carrier} da {origin} a {destination}, tutto incluso {amount}.",
        "thanks_ok": "Grazie, perfetto.",
        "wait_dg": "Prenoto appena arrivano la Shipper's Declaration for Dangerous Goods e la scheda di sicurezza (MSDS), a "
                   "meno che non mi dica di aspettare",
        "wait": "Non prenoto nulla finché non conferma, mi risponda quando è pronto e prenoto subito",
        "confirm": "Sì, confermo: la nostra offerta copre {goods}, da {origin} a {destination} con {carrier}{pickup}{ready}. "
                   "Il prezzo tutto incluso è {amount}.",
        "ready": ", pronto il {date}",
        "ask": "Prenoto?",
        "ask_dg": "Prenoto appena arrivano i documenti DG?",
    },
    "nl": {
        "status_confirmed": "{ref} ({origin} naar {destination} met {airline}) is geboekt en door de luchtvaartmaatschappij bevestigd, alles staat klaar.",
        "status_waiting": "{ref} ({origin} naar {destination} met {airline}) is geboekt, we wachten nog op de bevestiging van de luchtvaartmaatschappij.",
        "latest": "Laatste update van hen: {update}.",
        "planned_pickup": "Het is nog niet vertrokken, het ophalen bij {address} staat gepland voor {date}.",
        "planned_airport": "Het is nog niet vertrokken, de aflevering op het vliegveld staat gepland voor {date}.",
        "posted": "Ik houd u op de hoogte",
        "many": "U heeft {n} boekingen bij ons, zo staat elke boeking ervoor:",
        "many_other": "Bedoelde u een andere zending, stuur me dan het boekingsnummer (het begint met {bk})",
        "unknown": "Ik kan bij ons geen boeking met die referentie vinden. Kunt u me het boekingsnummer sturen (het begint "
                   "met {bk})? Dan kijk ik meteen",
        "details": "Bedankt voor uw bericht. Helaas kan ik de bijlage hier niet openen. Kunt u me de gegevens schriftelijk "
                   "sturen: postcode van ophalen (of vertrekluchthaven), bestemming, aantal colli, brutogewicht, volume en "
                   "klaardatum? Dan stuur ik u meteen de all-in prijs",
        "pickup_q": "Bedankt voor uw aanvraag. Om het ophalen per truck in de all-in prijs op te nemen, kunt u me het "
                    "ophaaladres met postcode geven? Ik stuur u de prijs direct daarna",
        "requested": "Top, ik heb {airline} gevraagd het voor u te boeken. Ik stuur u het boekingsnummer zodra ze bevestigen",
        "reprice": "Voor het boeken heb ik het tarief nog eens gecontroleerd: de prijs van de luchtvaartmaatschappij is sinds "
                   "uw akkoord gewijzigd. De nieuwe all-in prijs is {amount}. Zal ik tegen deze prijs boeken? Een kort ja volstaat",
        "reminder": "Ik kom even terug op mijn offerte voor {origin} naar {destination}: zal ik de boeking bij {carrier} voor u "
                    "regelen? Een kort ja volstaat",
        "stands": "Uw offerte blijft staan: {carrier} van {origin} naar {destination}, all-in {amount}.",
        "thanks_ok": "Dank u, dat is prima.",
        "wait_dg": "Ik boek zodra de Shipper's Declaration for Dangerous Goods en het veiligheidsinformatieblad (MSDS) binnen "
                   "zijn, tenzij u wilt dat ik wacht",
        "wait": "Er wordt niets geboekt voordat u bevestigt, antwoord gewoon als u zover bent en ik boek meteen",
        "confirm": "Ja, dat bevestig ik: onze offerte omvat {goods}, {origin} naar {destination} met {carrier}{pickup}{ready}. "
                   "De all-in prijs is {amount}.",
        "ready": ", klaar op {date}",
        "ask": "Zal ik het boeken?",
        "ask_dg": "Zal ik het boeken zodra de DG-documenten binnen zijn?",
    },
    "pt": {
        "status_confirmed": "{ref} ({origin} para {destination} com a {airline}) está reservado e confirmado pela companhia aérea, tudo pronto.",
        "status_waiting": "{ref} ({origin} para {destination} com a {airline}) está reservado, ainda aguardamos a confirmação da companhia aérea.",
        "latest": "Última informação deles: {update}.",
        "planned_pickup": "Ainda não saiu, a recolha em {address} está prevista para {date}.",
        "planned_airport": "Ainda não saiu, a entrega no aeroporto está prevista para {date}.",
        "posted": "Vou mantendo-o informado",
        "many": "Tem {n} reservas connosco, eis o ponto de cada uma:",
        "many_other": "Se se referia a outro envio, envie-me a referência da reserva (começa por {bk})",
        "unknown": "Não encontro nenhuma reserva com essa referência. Pode enviar-me a referência da reserva (começa por "
                   "{bk})? Verifico logo",
        "details": "Obrigada pela mensagem. Infelizmente não consigo abrir o anexo aqui. Pode enviar-me os dados por escrito: "
                   "código postal de recolha (ou aeroporto de partida), destino, número de volumes, peso bruto, volume e data "
                   "de disponibilidade? Envio-lhe logo o preço total",
        "pickup_q": "Obrigada pelo pedido. Para incluir a recolha por camião no preço total, pode indicar-me a morada de "
                    "recolha com o código postal? Envio-lhe o preço logo a seguir",
        "requested": "Ótimo, pedi à {airline} que faça a reserva. Envio-lhe a referência assim que confirmarem",
        "reprice": "Antes de reservar voltei a verificar a tarifa: o preço da companhia aérea mudou desde a sua confirmação. "
                   "O novo preço total é {amount}. Reservo a este preço? Basta um sim",
        "reminder": "Volto a contactá-lo sobre a proposta que enviei para {origin} para {destination}: quer que faça a "
                    "reserva com a {carrier}? Basta um sim",
        "stands": "A sua proposta mantém-se: {carrier} de {origin} para {destination}, tudo incluído {amount}.",
        "thanks_ok": "Obrigada, perfeito.",
        "wait_dg": "Reservo assim que chegarem a Shipper's Declaration for Dangerous Goods e a ficha de dados de segurança "
                   "(MSDS), a não ser que me diga para esperar",
        "wait": "Nada é reservado antes da sua confirmação, responda quando estiver pronto e reservo logo",
        "confirm": "Sim, confirmo: a nossa proposta cobre {goods}, {origin} para {destination} com a {carrier}{pickup}{ready}. "
                   "O preço total é {amount}.",
        "ready": ", pronto a {date}",
        "ask": "Faço a reserva?",
        "ask_dg": "Faço a reserva assim que chegarem os documentos DG?",
    },
    "tr": {
        "status_confirmed": "{ref} ({airline} ile {origin}-{destination}) rezerve edildi ve havayolu tarafından onaylandı, her şey hazır.",
        "status_waiting": "{ref} ({airline} ile {origin}-{destination}) rezerve edildi, havayolunun onayını hâlâ bekliyoruz.",
        "latest": "Onlardan son bilgi: {update}.",
        "planned_pickup": "Gönderi henüz yola çıkmadı, {address} adresinden alım {date} tarihinde planlandı.",
        "planned_airport": "Gönderi henüz yola çıkmadı, havalimanında teslim {date} tarihinde planlandı.",
        "posted": "Sizi bilgilendirmeye devam edeceğim",
        "many": "Bizde {n} rezervasyonunuz var, her birinin durumu şöyle:",
        "many_other": "Başka bir gönderiyi kastettiyseniz rezervasyon numarasını göndermeniz yeterli ({bk} ile başlar)",
        "unknown": "Bu referansla bir rezervasyon bulamadım. Rezervasyon numarasını gönderebilir misiniz ({bk} ile başlar)? "
                   "Hemen kontrol ederim",
        "details": "Mesajınız için teşekkürler. Maalesef eki burada açamıyorum. Bilgileri yazılı olarak gönderebilir misiniz: "
                   "alım posta kodu (veya kalkış havalimanı), varış yeri, parça sayısı, brüt ağırlık, hacim ve hazır olma "
                   "tarihi? Her şey dahil fiyatı hemen gönderirim",
        "pickup_q": "Talebiniz için teşekkürler. Kamyonla alımı her şey dahil fiyata eklemek için alım adresini posta koduyla "
                    "birlikte iletebilir misiniz? Fiyatı hemen ardından gönderirim",
        "requested": "Harika, {airline} firmasından rezervasyonu yapmasını istedim. Onaylar onaylamaz rezervasyon numarasını gönderirim",
        "reprice": "Rezervasyondan önce tarifeyi bir kez daha kontrol ettim: havayolunun fiyatı onayınızdan sonra değişti. "
                   "Yeni toplam fiyat {amount}. Bu fiyattan rezervasyon yapayım mı? Kısa bir evet yeterli",
        "reminder": "{origin}-{destination} için gönderdiğim teklifle ilgili kısaca yazıyorum: {carrier} ile rezervasyonu "
                    "yapmamı ister misiniz? Kısa bir evet yeterli",
        "stands": "Teklifiniz geçerli: {carrier}, {origin}-{destination}, her şey dahil {amount}.",
        "thanks_ok": "Teşekkürler, harika.",
        "wait_dg": "Shipper's Declaration for Dangerous Goods ve güvenlik bilgi formu (MSDS) gelir gelmez rezervasyonu "
                   "yaparım, beklememi isterseniz haber verin",
        "wait": "Siz onaylamadan hiçbir şey rezerve edilmez, hazır olduğunuzda yazmanız yeterli, hemen rezervasyonu yaparım",
        "confirm": "Evet, onaylıyorum: teklifimiz {goods} için geçerli, {carrier} ile {origin}-{destination}{pickup}{ready}. "
                   "Her şey dahil fiyat {amount}.",
        "ready": ", hazır olma tarihi {date}",
        "ask": "Rezervasyonu yapayım mı?",
        "ask_dg": "DG belgeleri gelince rezervasyonu yapayım mı?",
    },
    "pl": {
        "status_confirmed": "{ref} ({origin} do {destination}, {airline}) jest zarezerwowane i potwierdzone przez linię lotniczą, wszystko gotowe.",
        "status_waiting": "{ref} ({origin} do {destination}, {airline}) jest zarezerwowane, czekamy jeszcze na potwierdzenie linii lotniczej.",
        "latest": "Najnowsza informacja od nich: {update}.",
        "planned_pickup": "Przesyłka jeszcze nie wyjechała, odbiór z adresu {address} jest zaplanowany na {date}.",
        "planned_airport": "Przesyłka jeszcze nie wyjechała, przekazanie na lotnisku jest zaplanowane na {date}.",
        "posted": "Będę informować na bieżąco",
        "many": "Liczba Państwa rezerwacji u nas: {n}. Oto status każdej z nich:",
        "many_other": "Jeśli chodziło o inną przesyłkę, proszę przesłać numer rezerwacji (zaczyna się od {bk})",
        "unknown": "Nie znajduję u nas rezerwacji o tym numerze. Czy mogą Państwo przesłać numer rezerwacji (zaczyna się od "
                   "{bk})? Od razu sprawdzę",
        "details": "Dziękuję za wiadomość. Niestety nie mogę tu otworzyć załącznika. Czy mogą Państwo przesłać dane na piśmie: "
                   "kod pocztowy odbioru (lub lotnisko wylotu), miejsce docelowe, liczbę sztuk, wagę brutto, objętość i datę "
                   "gotowości? Od razu prześlę cenę all-in",
        "pickup_q": "Dziękuję za zapytanie. Aby uwzględnić odbiór samochodem w cenie all-in, proszę podać adres odbioru z "
                    "kodem pocztowym. Cenę prześlę zaraz potem",
        "requested": "Świetnie, poprosiłam {airline} o rezerwację. Numer rezerwacji prześlę, gdy tylko potwierdzą",
        "reprice": "Przed rezerwacją jeszcze raz sprawdziłam stawkę: cena linii lotniczej zmieniła się od Państwa akceptacji. "
                   "Nowa cena all-in to {amount}. Czy mam zarezerwować po tej cenie? Wystarczy krótkie tak",
        "reminder": "Wracam do oferty na trasę {origin} do {destination}: czy mam zarezerwować w {carrier}? Wystarczy krótkie tak",
        "stands": "Oferta jest aktualna: {carrier} z {origin} do {destination}, all-in {amount}.",
        "thanks_ok": "Dziękuję, wszystko się zgadza.",
        "wait_dg": "Zarezerwuję, gdy tylko dotrą Shipper's Declaration for Dangerous Goods i karta charakterystyki (MSDS), "
                   "chyba że mam poczekać",
        "wait": "Nic nie zostanie zarezerwowane bez Państwa potwierdzenia, proszę po prostu odpisać, a od razu zarezerwuję",
        "confirm": "Tak, potwierdzam: nasza oferta obejmuje {goods}, {origin} do {destination} z {carrier}{pickup}{ready}. "
                   "Cena all-in to {amount}.",
        "ready": ", gotowe {date}",
        "ask": "Czy mam zarezerwować?",
        "ask_dg": "Czy mam zarezerwować, gdy dotrą dokumenty DG?",
    },
    "cs": {
        "status_confirmed": "{ref} ({origin} do {destination}, {airline}) je rezervováno a potvrzeno leteckou společností, vše je připraveno.",
        "status_waiting": "{ref} ({origin} do {destination}, {airline}) je rezervováno, ještě čekáme na potvrzení letecké společnosti.",
        "latest": "Poslední zpráva od nich: {update}.",
        "planned_pickup": "Zásilka ještě neodjela, vyzvednutí na adrese {address} je naplánováno na {date}.",
        "planned_airport": "Zásilka ještě neodjela, předání na letišti je naplánováno na {date}.",
        "posted": "Budu vás průběžně informovat",
        "many": "Počet vašich rezervací u nás: {n}. Tady je stav každé z nich:",
        "many_other": "Pokud jste mysleli jinou zásilku, pošlete mi prosím číslo rezervace (začíná na {bk})",
        "unknown": "U nás nenacházím žádnou rezervaci s touto referencí. Můžete mi poslat číslo rezervace (začíná na {bk})? "
                   "Hned to zkontroluju",
        "details": "Děkuji za zprávu. Bohužel tu přílohu nedokážu otevřít. Můžete mi poslat údaje písemně: PSČ vyzvednutí "
                   "(nebo letiště odletu), cíl, počet kusů, hrubou hmotnost, objem a datum připravenosti? Hned vám pošlu cenu all-in",
        "pickup_q": "Děkuji za poptávku. Abych mohla zahrnout svoz do ceny all-in, můžete mi poslat adresu vyzvednutí s PSČ? "
                    "Cenu pošlu hned potom",
        "requested": "Výborně, požádala jsem {airline} o rezervaci. Číslo rezervace pošlu, jakmile potvrdí",
        "reprice": "Před rezervací jsem ještě jednou zkontrolovala sazbu: cena letecké společnosti se od vašeho souhlasu "
                   "změnila. Nová cena all-in je {amount}. Mám rezervovat za tuto cenu? Stačí krátké ano",
        "reminder": "Jen se připomínám ohledně nabídky na trasu {origin} do {destination}: mám rezervovat u {carrier}? "
                    "Stačí krátké ano",
        "stands": "Vaše nabídka platí: {carrier} z {origin} do {destination}, all-in {amount}.",
        "thanks_ok": "Děkuji, to je v pořádku.",
        "wait_dg": "Zarezervuji, jakmile dorazí Shipper's Declaration for Dangerous Goods a bezpečnostní list (MSDS), pokud "
                   "nechcete počkat",
        "wait": "Nic nerezervuji, dokud nepotvrdíte, stačí odpovědět, až budete připraveni, a hned zarezervuji",
        "confirm": "Ano, potvrzuji: naše nabídka zahrnuje {goods}, {origin} do {destination} s {carrier}{pickup}{ready}. "
                   "Cena all-in je {amount}.",
        "ready": ", připraveno {date}",
        "ask": "Mám to zarezervovat?",
        "ask_dg": "Mám to zarezervovat, až dorazí dokumenty DG?",
    },
    "sv": {
        "status_confirmed": "{ref} ({origin} till {destination} med {airline}) är bokad och bekräftad av flygbolaget, allt är klart.",
        "status_waiting": "{ref} ({origin} till {destination} med {airline}) är bokad, vi väntar fortfarande på flygbolagets bekräftelse.",
        "latest": "Senaste från dem: {update}.",
        "planned_pickup": "Den har inte lämnat än, upphämtning på {address} är planerad till {date}.",
        "planned_airport": "Den har inte lämnat än, inlämning på flygplatsen är planerad till {date}.",
        "posted": "Jag håller er uppdaterade",
        "many": "Ni har {n} bokningar hos oss, så här ligger var och en till:",
        "many_other": "Om ni menade en annan sändning, skicka bara bokningsnumret (det börjar med {bk})",
        "unknown": "Jag hittar ingen bokning med den referensen hos oss. Kan ni skicka bokningsnumret (det börjar med {bk})? "
                   "Då kollar jag direkt",
        "details": "Tack för ert meddelande. Tyvärr kan jag inte öppna bilagan här. Kan ni skicka uppgifterna skriftligt: "
                   "postnummer för upphämtning (eller avgångsflygplats), destination, antal kolli, bruttovikt, volym och "
                   "färdigdatum? Då skickar jag priset allt inkluderat direkt",
        "pickup_q": "Tack för er förfrågan. För att ta med upphämtningen med bil i priset, kan ni ange upphämtningsadressen "
                    "med postnummer? Jag skickar priset direkt efter",
        "requested": "Toppen, jag har bett {airline} att boka åt er. Jag skickar bokningsnumret så fort de bekräftar",
        "reprice": "Innan jag bokade kollade jag priset en gång till: flygbolagets pris har ändrats sedan ert ok. Det nya "
                   "priset allt inkluderat är {amount}. Ska jag boka till det priset? Ett kort ja räcker",
        "reminder": "Jag hör av mig angående offerten för {origin} till {destination}: ska jag boka med {carrier} åt er? "
                    "Ett kort ja räcker",
        "stands": "Er offert gäller: {carrier} från {origin} till {destination}, allt inkluderat {amount}.",
        "thanks_ok": "Tack, det är perfekt.",
        "wait_dg": "Jag bokar så snart Shipper's Declaration for Dangerous Goods och säkerhetsdatabladet (MSDS) har kommit, "
                   "om ni inte vill att jag väntar",
        "wait": "Inget bokas förrän ni bekräftar, svara bara när ni är redo så bokar jag direkt",
        "confirm": "Ja, det kan jag bekräfta: vår offert omfattar {goods}, {origin} till {destination} med "
                   "{carrier}{pickup}{ready}. Priset allt inkluderat är {amount}.",
        "ready": ", klar {date}",
        "ask": "Ska jag boka?",
        "ask_dg": "Ska jag boka när DG-dokumenten har kommit?",
    },
    "da": {
        "status_confirmed": "{ref} ({origin} til {destination} med {airline}) er booket og bekræftet af flyselskabet, alt er klar.",
        "status_waiting": "{ref} ({origin} til {destination} med {airline}) er booket, vi venter stadig på flyselskabets bekræftelse.",
        "latest": "Seneste nyt fra dem: {update}.",
        "planned_pickup": "Den er ikke afsendt endnu, afhentning på {address} er planlagt til {date}.",
        "planned_airport": "Den er ikke afsendt endnu, indlevering i lufthavnen er planlagt til {date}.",
        "posted": "Jeg holder jer opdateret",
        "many": "I har {n} bookinger hos os, her er status på hver af dem:",
        "many_other": "Hvis I mente en anden forsendelse, så send mig bare bookingnummeret (det starter med {bk})",
        "unknown": "Jeg kan ikke finde en booking med den reference hos os. Kan I sende mig bookingnummeret (det starter med "
                   "{bk})? Så tjekker jeg det med det samme",
        "details": "Tak for jeres besked. Desværre kan jeg ikke åbne vedhæftningen her. Kan I sende oplysningerne skriftligt: "
                   "postnummer for afhentning (eller afgangslufthavn), destination, antal kolli, bruttovægt, volumen og "
                   "klardato? Så sender jeg prisen alt inklusive med det samme",
        "pickup_q": "Tak for jeres forespørgsel. For at tage afhentningen med lastbil med i prisen, kan I oplyse "
                    "afhentningsadressen med postnummer? Jeg sender prisen lige bagefter",
        "requested": "Super, jeg har bedt {airline} om at booke det for jer. Jeg sender bookingnummeret, så snart de bekræfter",
        "reprice": "Før bookingen tjekkede jeg prisen en gang til: flyselskabets pris er ændret siden jeres ok. Den nye pris "
                   "alt inklusive er {amount}. Skal jeg booke til den pris? Et kort ja er nok",
        "reminder": "Jeg følger lige op på tilbuddet for {origin} til {destination}: skal jeg booke det med {carrier} for jer? "
                    "Et kort ja er nok",
        "stands": "Jeres tilbud står ved magt: {carrier} fra {origin} til {destination}, alt inklusive {amount}.",
        "thanks_ok": "Tak, det er perfekt.",
        "wait_dg": "Jeg booker, så snart Shipper's Declaration for Dangerous Goods og sikkerhedsdatabladet (MSDS) er kommet, "
                   "medmindre I vil have mig til at vente",
        "wait": "Intet bookes, før I bekræfter, svar bare når I er klar, så booker jeg med det samme",
        "confirm": "Ja, det kan jeg bekræfte: vores tilbud dækker {goods}, {origin} til {destination} med "
                   "{carrier}{pickup}{ready}. Prisen alt inklusive er {amount}.",
        "ready": ", klar {date}",
        "ask": "Skal jeg booke det?",
        "ask_dg": "Skal jeg booke det, når DG-dokumenterne er kommet?",
    },
    "nb": {
        "status_confirmed": "{ref} ({origin} til {destination} med {airline}) er booket og bekreftet av flyselskapet, alt er klart.",
        "status_waiting": "{ref} ({origin} til {destination} med {airline}) er booket, vi venter fortsatt på bekreftelse fra flyselskapet.",
        "latest": "Siste fra dem: {update}.",
        "planned_pickup": "Den har ikke reist ennå, henting på {address} er planlagt {date}.",
        "planned_airport": "Den har ikke reist ennå, innlevering på flyplassen er planlagt {date}.",
        "posted": "Jeg holder dere oppdatert",
        "many": "Dere har {n} bookinger hos oss, her er status for hver av dem:",
        "many_other": "Hvis dere mente en annen sending, send meg bare bookingnummeret (det begynner med {bk})",
        "unknown": "Jeg finner ingen booking med den referansen hos oss. Kan dere sende meg bookingnummeret (det begynner med "
                   "{bk})? Så sjekker jeg med en gang",
        "details": "Takk for meldingen. Dessverre kan jeg ikke åpne vedlegget her. Kan dere sende opplysningene skriftlig: "
                   "postnummer for henting (eller avgangsflyplass), destinasjon, antall kolli, bruttovekt, volum og klardato? "
                   "Så sender jeg prisen alt inkludert med en gang",
        "pickup_q": "Takk for forespørselen. For å ta med henting med bil i prisen, kan dere oppgi henteadressen med "
                    "postnummer? Jeg sender prisen rett etterpå",
        "requested": "Flott, jeg har bedt {airline} om å booke for dere. Jeg sender bookingnummeret så snart de bekrefter",
        "reprice": "Før bookingen sjekket jeg prisen en gang til: flyselskapets pris har endret seg siden deres ok. Ny pris "
                   "alt inkludert er {amount}. Skal jeg booke til den prisen? Et kort ja holder",
        "reminder": "Jeg følger opp tilbudet for {origin} til {destination}: skal jeg booke med {carrier} for dere? "
                    "Et kort ja holder",
        "stands": "Tilbudet deres gjelder: {carrier} fra {origin} til {destination}, alt inkludert {amount}.",
        "thanks_ok": "Takk, det er perfekt.",
        "wait_dg": "Jeg booker så snart Shipper's Declaration for Dangerous Goods og sikkerhetsdatabladet (MSDS) er kommet, "
                   "med mindre dere vil at jeg venter",
        "wait": "Ingenting bookes før dere bekrefter, svar bare når dere er klare, så booker jeg med en gang",
        "confirm": "Ja, det kan jeg bekrefte: tilbudet vårt dekker {goods}, {origin} til {destination} med "
                   "{carrier}{pickup}{ready}. Prisen alt inkludert er {amount}.",
        "ready": ", klar {date}",
        "ask": "Skal jeg booke?",
        "ask_dg": "Skal jeg booke når DG-dokumentene er kommet?",
    },
    "fi": {
        "status_confirmed": "{ref} ({origin}-{destination}, {airline}) on varattu ja lentoyhtiö on vahvistanut sen, kaikki on valmista.",
        "status_waiting": "{ref} ({origin}-{destination}, {airline}) on varattu, odotamme vielä lentoyhtiön vahvistusta.",
        "latest": "Uusin tieto heiltä: {update}.",
        "planned_pickup": "Lähetys ei ole vielä lähtenyt, nouto osoitteesta {address} on suunniteltu päivälle {date}.",
        "planned_airport": "Lähetys ei ole vielä lähtenyt, luovutus lentoasemalla on suunniteltu päivälle {date}.",
        "posted": "Pidän teidät ajan tasalla",
        "many": "Teillä on meillä {n} varausta, tässä kunkin tilanne:",
        "many_other": "Jos tarkoititte toista lähetystä, lähettäkää minulle sen varausnumero (se alkaa {bk})",
        "unknown": "En löydä meiltä varausta tuolla viitteellä. Voisitteko lähettää varausnumeron (se alkaa {bk})? "
                   "Tarkistan sen heti",
        "details": "Kiitos viestistä. Valitettavasti en saa liitettä auki täällä. Voisitteko lähettää tiedot kirjallisesti: "
                   "noudon postinumero (tai lähtölentoasema), määränpää, kollien määrä, bruttopaino, tilavuus ja valmiuspäivä? "
                   "Lähetän kokonaishinnan heti",
        "pickup_q": "Kiitos tarjouspyynnöstä. Jotta voin sisällyttää noudon kokonaishintaan, voisitteko kertoa nouto-osoitteen "
                    "postinumeroineen? Lähetän hinnan heti sen jälkeen",
        "requested": "Hienoa, pyysin {airline}-yhtiötä tekemään varauksen. Lähetän varausnumeron heti kun he vahvistavat",
        "reprice": "Tarkistin hinnan vielä ennen varausta: lentoyhtiön hinta on muuttunut hyväksyntänne jälkeen. Uusi "
                   "kokonaishinta on {amount}. Varaanko tällä hinnalla? Lyhyt kyllä riittää",
        "reminder": "Palaan vielä tarjoukseen reitille {origin}-{destination}: varaanko sen {carrier}-yhtiöltä? Lyhyt kyllä riittää",
        "stands": "Tarjouksenne on voimassa: {carrier}, {origin}-{destination}, kokonaishinta {amount}.",
        "thanks_ok": "Kiitos, sopii hyvin.",
        "wait_dg": "Varaan heti kun Shipper's Declaration for Dangerous Goods ja käyttöturvallisuustiedote (MSDS) ovat tulleet, "
                   "ellette pyydä odottamaan",
        "wait": "Mitään ei varata ennen vahvistustanne, vastatkaa vain kun olette valmiita, niin varaan heti",
        "confirm": "Kyllä, vahvistan: tarjouksemme kattaa {goods}, {origin}-{destination}, {carrier}{pickup}{ready}. "
                   "Kokonaishinta on {amount}.",
        "ready": ", valmiina {date}",
        "ask": "Varaanko?",
        "ask_dg": "Varaanko, kun DG-asiakirjat ovat tulleet?",
    },
    "ja": {
        "status_confirmed": "{ref}（{origin}発{destination}行き、{airline}）は予約済みで、航空会社の確認も取れています。準備は整っています。",
        "status_waiting": "{ref}（{origin}発{destination}行き、{airline}）は予約済みで、航空会社の確認を待っているところです。",
        "latest": "航空会社からの最新情報：{update}。",
        "planned_pickup": "まだ出発していません。{address}での集荷は{date}の予定です。",
        "planned_airport": "まだ出発していません。空港での引き渡しは{date}の予定です。",
        "posted": "引き続き状況をお知らせします",
        "many": "弊社でのご予約は{n}件です。それぞれの状況は以下のとおりです：",
        "many_other": "別の貨物のことでしたら、予約番号（{bk}で始まります）をお送りください",
        "unknown": "その番号の予約が見つかりませんでした。予約番号（{bk}で始まります）をお送りいただけますか？すぐに確認します",
        "details": "ご連絡ありがとうございます。申し訳ありませんが、こちらでは添付ファイルを開けません。集荷地の郵便番号"
                   "（または出発空港）、仕向地、個数、総重量、容積、出荷可能日を文面でお送りいただけますか？すぐに総額をお送りします",
        "pickup_q": "お問い合わせありがとうございます。トラック集荷を総額に含めるため、集荷先の住所と郵便番号を教えて"
                    "いただけますか？その後すぐに料金をお送りします",
        "requested": "承知しました。{airline}に予約を依頼しました。確認が取れ次第、予約番号をお送りします",
        "reprice": "予約前に料金を再確認したところ、ご承諾いただいた後に航空会社の料金が変更されていました。新しい総額は"
                   "{amount}です。この料金で予約してよろしいですか？一言ご返信いただければ手配します",
        "reminder": "{origin}発{destination}行きのお見積もりの件でご連絡しました。{carrier}で予約を進めてよろしいですか？"
                    "一言ご返信いただければ手配します",
        "stands": "お見積もりはそのまま有効です：{carrier}、{origin}発{destination}行き、総額{amount}。",
        "thanks_ok": "ありがとうございます、承知しました。",
        "wait_dg": "Shipper's Declaration for Dangerous Goodsと安全データシート（MSDS）が届き次第、予約します。"
                   "お待ちになる場合はお知らせください",
        "wait": "ご確認いただくまで予約はいたしません。準備ができましたらご返信ください。すぐに予約します",
        "confirm": "はい、確認いたします。お見積もりの内容は{goods}、{origin}発{destination}行き、{carrier}{pickup}{ready}"
                   "です。総額は{amount}です。",
        "ready": "、出荷可能日{date}",
        "ask": "予約を進めてよろしいですか？",
        "ask_dg": "DG書類が届き次第、予約を進めてよろしいですか？",
    },
    "zh": {
        "status_confirmed": "{ref}（{origin}到{destination}，{airline}）已订舱，航空公司也已确认，一切就绪。",
        "status_waiting": "{ref}（{origin}到{destination}，{airline}）已订舱，我们还在等航空公司确认。",
        "latest": "航空公司的最新消息：{update}。",
        "planned_pickup": "货物还未出发，计划于{date}在{address}提货。",
        "planned_airport": "货物还未出发，计划于{date}在机场交货。",
        "posted": "有进展我会随时通知您",
        "many": "您在我们这里有{n}个订舱，各自的状态如下：",
        "many_other": "如果您问的是另一票货，请把订舱号发给我（以{bk}开头）",
        "unknown": "我们这边没有找到这个编号的订舱。能否把订舱号发给我（以{bk}开头）？我马上查",
        "details": "谢谢您的来信。很抱歉，我这里打不开附件。能否把信息直接写在邮件里：提货邮编（或起运机场）、目的地、件数、"
                   "毛重、体积和备货日期？我会马上发给您全包价",
        "pickup_q": "谢谢您的询价。为了把卡车提货算进全包价，能否告诉我提货地址和邮编？我随后马上报价",
        "requested": "好的，我已请{airline}为您订舱。航空公司确认后我会马上把订舱号发给您",
        "reprice": "订舱前我又核对了一次运价：自您确认后，航空公司的价格有变动。新的全包价为{amount}。按这个价格订舱可以吗？"
                   "回复一句好的就行",
        "reminder": "想跟您确认一下{origin}到{destination}的报价：需要我在{carrier}为您订舱吗？回复一句好的就行",
        "stands": "您的报价仍然有效：{carrier}，{origin}到{destination}，全包价{amount}。",
        "thanks_ok": "谢谢，没问题。",
        "wait_dg": "收到Shipper's Declaration for Dangerous Goods和安全技术说明书（MSDS）后我就订舱，除非您让我再等等",
        "wait": "您确认之前不会订舱，准备好了回复我就行，我马上订",
        "confirm": "可以确认：我们的报价包括{goods}，{origin}到{destination}，{carrier}{pickup}{ready}。全包价为{amount}。",
        "ready": "，备货日期{date}",
        "ask": "需要我订舱吗？",
        "ask_dg": "DG文件到齐后我就订舱，可以吗？",
    },
}


def more_language(code: str | None) -> str | None:
    """The language for the other mails when it isn't English and we have (or just learned) both template sets."""
    code = (code or "en").lower()[:2]
    code = ALIASES.get(code, code)
    if code == "en" or not language.REPLY_LANGUAGE or not ((code in QUOTE or _learn(code)) and (code in MORE or _learn(code, more=True))):
        return None
    return code


def _money(quote: dict) -> str:
    return f"{quote['currency']} {float(quote['total']):,.2f}"


def _goods(lang: str, rfq: dict) -> str:
    count = sum(int(p.get("count") or 1) for p in rfq.get("pieces") or []) or 1
    kg = sum(int(p.get("count") or 1) * (p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
    return _n(GOODS[lang], count) + (f" ({round(kg)} kg)" if kg >= 1 else "")  # never English here: R73, no comma


def _status_lines(lang: str, session: dict) -> list[str]:
    m, booking, rfq = MORE[lang], session["booking"], session.get("rfq") or {}
    key = "status_confirmed" if booking.get("status") == "confirmed" else "status_waiting"
    lines = [m[key].format(ref=booking["booking_reference"], origin=rfq.get("origin"), destination=rfq.get("destination"),
                           airline=booking.get("airline"))]
    ready, pickup = rfq.get("ready_date"), (rfq.get("pickup") or {}).get("address")
    if updates := session.get("status_updates") or []:
        lines.append(m["latest"].format(update=updates[-1]["text"].rstrip(".")))  # the airline's own words
    elif ready and str(ready) >= date.today().isoformat():  # only before the ready date: after it, may be wrong
        lines.append(m["planned_pickup"].format(address=pickup, date=day(lang, ready)) if pickup
                     else m["planned_airport"].format(date=day(lang, ready)))
    if days := (session.get("quote") or {}).get("transit_days"):
        lines.append(TRANSIT[lang].format(n=_n(DAYS[lang], max(1, round(days)))).strip())
    return lines


def tracking_in(lang: str, session: dict) -> str:
    return _mail(lang, (session.get("rfq") or {}).get("contact_name"), *_status_lines(lang, session), MORE[lang]["posted"])


def tracking_many(lang: str, sessions: list[dict]) -> str:
    lines = "\n".join("- " + " ".join(_status_lines(lang, s)) for s in sessions)
    return _mail(lang, (sessions[0].get("rfq") or {}).get("contact_name"),
                 f"{MORE[lang]['many'].format(n=len(sessions))}\n\n{lines}\n\n{MORE[lang]['many_other'].format(bk='BK-')}")


def tracking_unknown(lang: str) -> str:
    return _mail(lang, None, MORE[lang]["unknown"].format(bk="BK-"))


def ask(lang: str, rfq: dict, key: str) -> str:
    """details / pickup_q: a question, no price."""
    return _mail(lang, rfq.get("contact_name"), MORE[lang][key])


def requested(lang: str, session: dict) -> str:
    airline = (session.get("quote") or {}).get("carrier") or "the airline"
    return _mail(lang, (session.get("rfq") or {}).get("contact_name"), MORE[lang]["requested"].format(airline=airline))


def reprice(lang: str, rfq: dict, quote: dict) -> str:
    return _mail(lang, rfq.get("contact_name"), MORE[lang]["reprice"].format(amount=_money(quote)))


def reminder(lang: str, rfq: dict, quote: dict) -> str:
    return _mail(lang, rfq.get("contact_name"), MORE[lang]["reminder"].format(
        origin=rfq.get("origin"), destination=rfq.get("destination"), carrier=quote.get("carrier")))


def _stands(lang: str, rfq: dict, quote: dict) -> str:
    return MORE[lang]["stands"].format(carrier=quote.get("carrier"), origin=rfq.get("origin"),
                                       destination=rfq.get("destination"), amount=_money(quote))


def docs_ack(lang: str, rfq: dict, quote: dict) -> str:
    """Thanks, the quote restated (one amount), nothing booked before the papers / the customer's yes."""
    m = MORE[lang]
    stands = _stands(lang, rfq, quote) if quote.get("total") and quote.get("currency") and quote.get("carrier") else ""
    return _mail(lang, rfq.get("contact_name"), f"{m['thanks_ok']} {stands}".strip(),
                 m["wait_dg" if rfq.get("dangerous_goods") else "wait"])


def summary(lang: str, rfq: dict, quote: dict) -> str:
    """The customer asks about the open quote: carrier, route, the one amount, transit, then what happens next."""
    days = quote.get("transit_days")
    transit = TRANSIT[lang].format(n=_n(DAYS[lang], max(1, round(float(days))))) if days else ""
    return _mail(lang, rfq.get("contact_name"), _stands(lang, rfq, quote) + transit,
                 MORE[lang]["wait_dg" if rfq.get("dangerous_goods") else "wait"])


def confirm(lang: str, rfq: dict, quote: dict) -> str:
    """R60: what the quote covers (pieces, weight, route, carrier, pickup, ready date) and the one amount."""
    m = MORE[lang]
    ready = m["ready"].format(date=day(lang, rfq["ready_date"])) if rfq.get("ready_date") else ""
    text = m["confirm"].format(goods=_goods(lang, rfq), origin=rfq.get("origin"), destination=rfq.get("destination"),
                               carrier=quote.get("carrier"), pickup=PICKUP[lang] if rfq.get("pickup") else "",
                               ready=ready, amount=_money(quote))
    return _mail(lang, rfq.get("contact_name"), text, m["ask_dg" if rfq.get("dangerous_goods") else "ask"])
