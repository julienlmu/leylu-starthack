"""Booking agent: a customer reply to our quote → accept / decline / question → book by rate ID and confirm.

Also records the airline's "Booking BK-… confirmed" mail and tells the customer.
"""

import os
import unicodedata
from email.utils import parseaddr
import re
import time
import threading

import amendments
import language
import short_mail
from extract import CARGO_FACT
import llm
import price_match
import quote_style
import requote
from backend import now
from carriers import load_carriers
from inbox import latest_text, mail_data, reply_data
from rfq_agent import hand_over, sent_at
from router import CONFIRMED
from humanizer import follow_up_text
from templates import booking_confirmed_text, booking_text, confirm_text, docs_ack_text, reprice_text, tracking_text

# "confirm" is a yes only when the customer confirms ("I confirm.", "We confirm the booking.", "Confirmed.",
# "Please confirm.", "confirm the booking, please"), never when they ask us to ("Please confirm you can do 3 pallets",
# "please confirm receipt", "confirm your offer is valid until Friday", "We confirm receipt of your offer") (#167, #185)
CONFIRM_YES = (r"(?:i|we)(?: hereby)? (?:confirm|confrim)(?=\s*(?:[.!]|$|,\s*(?:please\s+)?(?:book|go ahead|proceed)|"
               r"(?:the|our) (?:booking|order)\b|(?:it|this)\s*[.!]?\s*$))|"
               r"(?:confirm|confrim) (?:the|our) (?:booking|order)(?=\s*(?:[.!,]|$|please|thanks?|thank you))|"
               r"^\s*(?:please\s+)?(?:confirmed|confirm|confrim)(?=\s*(?:[.!]|,\s*(?:please\s+)?(?:book|go ahead|proceed)|$))|"
               r"(?:ich|wir) bestätigen? (?:die|den) (?:buchung|auftrag)\b|bestätigen wir (?:die|den) (?:buchung|auftrag)\b|"
               r"(?:ich|wir) bestätigen?(?=\s*[.!]?\s*$)|"
               r"^\s*bestätigt(?=\s*[.!]?\s*$)")
ACCEPT = re.compile(r"\b(accept\w*|book\w*(?!\s+(?:date|reference|number|details|confirmation|status))|go ahead|proceed|"
                    + CONFIRM_YES + r"|agreed|deal|ok|okay|yes|einverstanden|buchen|"
                    r"d'accord|réserve\w*|acepto|reserv\w*|rezerw\w*|akceptuj\w*|zgoda|"
                    # youth / formal / regional English (Ulas): "lgtm", "say less", "works for me", "we are agreeable"
                    r"lgtm|say less|works for me|(?:we are|we're|i am) agreeable|righto|do the needful|"
                    # slang, dialect and typos: "yep", "go for it", "passt scho", Swiss "isch guet, bueche", "bokk", "procced"
                    r"yep|yup|yeah|yea|go for it|let'?s do (?:it|this)|let'?s go ahead|sounds (?:good|great|fine)|"
                    r"looks (?:good|great|fine)|approved?|passt|geht klar|gebongt|mach(?:en)? (?:mer|wir)|isch guet|"
                    r"b[uü]e?che|ja,? (?:bitte|gerne)|bokk\w*|ac+ept\w*|pro(?:c+e+d+|cede)|go ah(?:ea|ae)d|"
                    # trap 20: Hungarian, Korean, Arabic yes / book / agree
                    r"igen|rendben|elfogad\w*|foglal\w*|네|예약\w*|좋습니다|진행\w*|수락\w*|نعم|موافق\w*|أوافق|احجز\w*|نقبل)\b"
                    r"|👍|✅|✔️?|👌|🤝",
                    re.I | re.M)
NEW_REQUEST = re.compile(r"\b(?:another|a\s+new|a\s+second|an?\s+additional|one\s+more|a\s+further|also\s+(?:need|have)\s+a|"
                         r"weitere[nr]?|noch\s+eine[nr]?|eine\s+neue|une\s+autre|nouvelle|otra|nueva|un'?\s*altra|"
                         r"nuova)\s+(?:\w+\s+){0,2}?(?:shipment|request|quote|quotation|rfq|order|lot|consignment|"
                         r"sendung|anfrage|angebot|auftrag|envoi|demande|cotizaci[oó]n|env[ií]o|spedizione|richiesta)\b",
                         re.I)
# After a booking, only a plain thank-you needs no person: "please cancel" or "change the date" must still reach one.
# Session 131: "Teşekkürler Lena, havayolunun onayını bekliyorum" went to a person: Turkish (and more) thanks too.
THANKS = re.compile(r"\b(thank\w*|thx|cheers|dank\w*|merci|gracias|grazie|obrigad\w*|dzięk\w*|bedank\w*|"
                    r"te[şs]ekk[üu]r\w*|sa[ğg]\s?ol\w*|eyvallah|mersi|vielen\s+dank|danke\w*|cordialement\s+merci|"
                    r"muchas\s+gracias|mil\s+gracias|ringrazi\w*|agradec\w*|dankjewel|dank\s+je|dank\s+u|"
                    # session 136: "waiting for the airline's confirmation" alone is a plain acknowledgment too
                    r"onay\w*\s+bekl\w*|waiting\s+for\s+(?:the\s+|your\s+)?(?:\w+'s\s+)?confirmation|"
                    r"look\w*\s+forward\s+to\s+(?:the\s+|your\s+)?confirmation|warte\w*\s+auf\s+(?:die\s+)?best[äa]tigung|"
                    r"attends?\s+(?:la\s+)?confirmation|esper\w*\s+(?:la\s+)?confirmaci[oó]n|attendo\s+(?:la\s+)?conferma|"
                    r"aguard\w*\s+(?:a\s+)?confirma[çc][ãa]o|wacht\w*\s+op\s+(?:de\s+)?bevestiging)\b", re.I)
DECLINE = re.compile(r"\b(no|not|don't|won'?t|will not|decline\w*|cancel\w*|expensive|nicht|kein\w*|teuer|absage\w*|pas|annule\w*|"
                     r"hay[ıi]r|iptal\w*|vazge[çc]\w*|pahal[ıi]|istemiyor\w*|gerek\s+yok|storn\w*|"
                     r"caro|nie|"
                     # trap 20: Hungarian, Korean, Arabic no / decline / too expensive / cancel
                     r"nem|elutasít\w*|drága|아니요|아니오|거절\w*|비싸\w*|취소\w*|لا|نرفض|رفض\w*|مرتفع|غالي|إلغاء|"
                     # slang: "nope", "nah", "pass on this one", "too pricey", "lassen wir", "nö"
                     r"nope|nah|(?<![:=]\s)(?<![:=])(?:nein|nee|nö)|pricey|forget it|"  # "Gefahrgut: nein" is a form field, no decline
                     r"(?:(?:we|i)(?:'ll| will) )?pass(?: on (?:this|it|that)(?: one| time| offer| quote)?)?(?=\s*(?:[.!,]|for now|$))|"
                     r"went with (?:another|a different|someone)|lassen wir(?: es| das)?(?: lieber)?(?: bleiben| sein)?"
                     r"(?=\s*(?:[.!,]|danke|$)))(?!\w)", re.I)
# "OK, book it, but change the pickup to the 30th": a yes with a change is not a plain yes, it needs a person.
CHANGE = re.compile(r"\b(but|however|instead|change\w*|chang\w*|different|update\w*|correct\w*|amend\w*|"
                    r"reschedul\w*|postpone\w*|aber|jedoch|stattdessen|ändern|geändert|änderung|verschieb\w*|"
                    r"mais|pero|ma|ولكن|لكن|하지만|그런데|다만|viszont|azonban)\b", re.I)
# "OK, if you can do it 10% cheaper we will book": a yes on a condition is no yes. Never booked, a person decides.
CONDITION = re.compile(r"\b(confirm\w*\s+(?:the|our|this)\s+booking\s+(?:date|time|details|slot|with)|if you (?:can|could)|only if|unless|if (?:the )?(?:transit|price|rate|total|cost|delivery|arrival)|"
                       r"if it (?:arrives|is|can|leaves|departs|gets)|provided|as long as|on condition|cheaper|discount|lower (?:the )?price|"
                       r"fewer|günstiger|billiger|rabatt|sofern|unter der bedingung|pod warunkiem|taniej|zniżk\w*|"
                       r"moins cher|remise|más barato|descuento|più economico|sconto)\b|\d\s?%", re.I)
# "nie mamy zastrzeżeń" (Polish: we have no objections) is a yes, not the decline word "nie"
NO_OBJECTION = re.compile(r"\b(nie mamy zastrzeżeń|no objections?|keine einwände|keine bedenken)\b", re.I)
NEGATED_ACCEPT = re.compile(r"\b(?:will not|won't|wont|do not|don't|cannot|can't|not able to|unable to|not|nicht)"
                            r"\s+(?:(?!wait\b|hesitate\b)\w+\s+){0,2}?(?:go ahead|proceed|book\w*|accept\w*|buchen|annehmen)\b",
                            re.I)  # "can't wait to book" / "don't hesitate to book" are a yes
# R39: "Thank you, good point. We will send you the dangerous goods documents shortly." is no yes and no question:
# we answer it ourselves (thanks, ready to book on their word) instead of handing it to a person. DOCS_ACK=off: off.
DOCS_ACK = os.environ.get("DOCS_ACK", "on").lower() != "off"
DOCS_PROMISE_WORDS = re.compile(r"\b(document\w*|declaration|safety data sheet|msds|sds|dgd|papers?|paperwork|"
                                r"unterlagen|dokument\w*|sicherheitsdatenbl\w+|erklärung)\b", re.I)
DOCS_PROMISE = re.compile(
    # R63 "We’ll send you the dangerous goods documents shortly"; the verb alone ("I'll forward your offer") is no promise
    r"(?:(?:\bwill|['’]ll)\s+(?:send|forward|provide)\b|\b(?:send (?:you |them |it )?(?:shortly|soon|later|today|"
    r"tomorrow)|attached|attach\w*|follow\w* (?:shortly|soon)|on (?:its|their) way|schicken|senden|nachreichen|anbei)\b)"
    r"[^?]{0,160}?\b(document\w*|declaration|safety data sheet|msds|sds|dgd|papers?|paperwork|unterlagen|"
    r"dokument\w*|sicherheitsdatenbl\w+|erklärung)\b|"
    r"\b(document\w*|declaration|safety data sheet|msds|sds|dgd|papers?|paperwork|unterlagen|dokument\w*)\b"
    r"[^?]{0,80}?\b(will follow|follow\w* (?:shortly|soon)|(?:are|is) attached|on (?:its|their) way|kommen)\b", re.I)


# 5U's DG follow-ups (rounds 39-41): the customer asks for the quote again, or will get back to us.
QUOTE_AGAIN = re.compile(r"\b(?:send|resend|share|repeat|forward|confirm|give)\b[^.?!]{0,40}\b(?:quote|quotation|offer|"
                         r"price|angebot)\b|\b(?:quote|offer|price|angebot)\b[^.?!]{0,20}\b(?:again|nochmal|noch einmal)\b",
                         re.I)
# A request for a *different* quote is a change for a person, never a recap of the old one: "revised quote for
# 3 pallets instead of 2", "quote again but for delivery to Munich", "price without the pickup".
QUOTE_CHANGE = re.compile(r"\b(?:revis\w*|new|updated?\s+(?:quote|price|offer)|instead|different|other|without|excluding|"
                          r"only|but|except|change\w*|amend\w*|adjust\w*|cheaper|lower|discount|deliver\w*\s+to|delivery|"
                          r"door|incoterms?|ddp|dap|exw|for\s+\d|\d+\s*(?:pallets?|pieces?|pcs|cartons?|crates?|kg|cbm|m3|tons?)|"
                          r"statt|ohne|neu\w*|ander\w*|nur|günstiger)\b", re.I)
WILL_GET_BACK = re.compile(r"\b(?:get back to you|come back to you|let you know|will check|i'?ll check|i will check|"
                           r"melde mich|gebe .{0,15}bescheid|komme .{0,20}zurück)\b", re.I)


# "ok, I'll check internally and get back to you" is no yes yet (the LLM reads it); "book it, I'll let you know the
# pickup time" still books.
CHECK_FIRST = re.compile(r"\b(?:get back to you|come back to you|revert|(?:will|i'?ll|we'?ll) check|check (?:internally|with)|"
                         r"melde\w* mich|komme\w* zurück)\b|"
                         # #217's Korean/Hungarian/Arabic yes-words also sit in "don't book yet" / "before booking":
                         # a negation, "yet", "before" or "wait" there is never a rule-yes (the model reads it)
                         r"마세요|말아|않|전에|아직|기다리|"
                         r"\bne\b|\bnem\b|\bmég\b|előtt|várj|"
                         r"\bلا\b|ليس|لم|بعد|قبل|انتظر|ننتظر", re.I)
# R39: "Please hold off on booking for now." was read as a yes ("booking") and booked. A hold is never a yes.
HOLD = re.compile(r"\b(hold off|hold on|on hold|not yet|don'?t book|do not book|"
                  r"wait (?:before|with) (?:the )?booking|before (?:we|you) book|noch nicht|nicht buchen)\b|"
                  r"\b(?:not|n't)\b[^.!\n]{0,25}\byet\b", re.I)
# "I'll check ... and get back to you": they decide later. We wait (the quote stays open), no person needed.
LATER = re.compile(r"\b(get back to you|come back to you|revert|let you know|check (?:on|with|internally)|"
                   r"melde\w* mich|komme\w* zurück|r(?:ü|ue)ckmeld\w*)\b", re.I)
# R39/R40: the documents a DG quote waited for arrive ("please find attached the shipper's declaration"): thanked and
# asked for the go-ahead, never booked on the papers alone (a yes in the same mail books as usual)
DOCS_SENT = re.compile(r"\b(attached|enclosed|please find|here (?:are|is)|anbei|im anhang|beigefügt)\b", re.I)
DOCS_BOOK = os.environ.get("DOCS_BOOK", "on").lower() != "off"
# R60: "could you please confirm that your offer covers 11 pieces …?" is answered from our data (before HOLD)
CONFIRM_ANSWERS = os.environ.get("CONFIRM_ANSWERS", "on").lower() != "off"
# Review: only a confirm-question about what we already quoted (its pieces/weight) gets "yes"; customs, insurance,
# delivery dates, transit, validity, receipts or a "not X" correction go the usual way (never a false promise).
OTHER_TOPIC = re.compile(r"\b(includ\w*|customs|clearance|insur\w*|deliver\w*|arriv\w*|transit|valid\w*|receipt|"
                         r"received|not|nicht|instead|statt|by \d|until|bis zum|zoll|versicher\w*)\b", re.I)
CONFIRM_PCS = re.compile(r"\b(\d{1,4})\s*(?:pieces?|pcs|packages?|cartons?|pallets?|colli|crates?|boxes)\b", re.I)
CONFIRM_KG = re.compile(r"\b(\d[\d.,]*)\s*(?:kg|kgs)\b", re.I)


# Review of #165 (Julien): the object of "confirm" must be our offer ("confirm that your offer covers 11 pieces"),
# never the cargo ("confirm the 11 pieces can be stacked"); and no airport or date other than ours may be named.
CONFIRM_OFFER = re.compile(r"\bconfirm(?: that)? (?:your|the|this) (?:offer|quote|quotation|rate|price) "
                           r"(?:covers|is for)\b", re.I)
CODE = re.compile(r"\b[A-Z]{3}\b")  # an airport code as customers write it (capitals only)
NOT_CODES = {"EUR", "USD", "CHF", "GBP", "PCS", "KGS", "CBM", "SDS", "DGD", "AWB", "ETA", "ETD", "VAT", "POD", "SLI",
             "THE", "AND", "FOR"}
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
                                     1)}
MONTHS.update({"mär": 3, "mrz": 3, "mai": 5, "okt": 10, "dez": 12})
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\.?\s*(jan|feb|m[aä]r|mrz|apr|ma[yi]|jun|jul|aug|sep|o[ck]t|nov|de[cz])"
                       r"[a-z]*\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b|"
                       r"\b(\d{1,2})[./](\d{1,2})\b(?![.,]\d)|\b\d{4}-(\d{2})-(\d{2})\b", re.I)


def _dates(text: str) -> set[tuple[int, int]]:
    """(day, month) of every date the mail names: 27 Nov, Nov 27th, 27.11., 27/11, 2026-11-27."""
    found = set()
    for m in DAY_MONTH.finditer(text):
        if m[1]:
            found.add((int(m[1]), MONTHS[m[2][:3].lower()]))
        elif m[3]:
            found.add((int(m[4]), MONTHS[m[3][:3].lower()]))
        elif m[5]:
            found.add((int(m[5]), int(m[6])))
        else:
            found.add((int(m[8]), int(m[7])))
    return found


def _kg(value: str) -> float | None:
    try:
        if "," in value and "." not in value:  # 1,674 (thousands) or 1674,5 (decimal)
            head, _, tail = value.rpartition(",")
            return float(value.replace(",", "")) if len(tail) == 3 else float(head.replace(",", "") + "." + tail)
        if "," in value:  # 1.674,5
            return float(value.replace(".", "").replace(",", "."))
        if value.count(".") == 1 and len(value.rsplit(".", 1)[1]) == 3:  # 1.674 (German thousands)
            return float(value.replace(".", ""))
        return float(value.replace(".", "")) if value.count(".") > 1 else float(value)
    except ValueError:
        return None


# Third review of #165 (Julien): a whitelist, not a blocklist. Strip the confirm phrase, our numbers with units, our
# codes, pickup address, dates and these fillers; anything left ("cargo aircraft only", "collect on Saturday", "door to
# door to Mumbai", "by air to Delhi", "return shipment") goes the usual way (a person), never "yes, I can confirm".
CONFIRM_FILLER = set("""please kindly could can would you also just confirm confirmed that your the this our offer quote
quotation rate price covers cover is for with a an gross total weight of and to from on at pickup pick up ready hi hello
dear thanks thank regards best kind many hold off booking for now we i pieces piece pcs kg kgs
""".split())
GREETING = re.compile(r"^\s*(?:hi|hello|dear|good (?:morning|afternoon|evening))\b[^\n?]{0,40}$", re.I)
SIGN_OFF = re.compile(r"^\s*(?:(?:best|kind|warm|many)?\s*regards|thanks?(?: you)?(?: in advance)?|cheers|br|"
                      r"mit freundlichen gr\w+|viele gr\w+|beste gr\w+)\b[\s,.!]*$", re.I)


def _leftover(text: str, rfq: dict) -> list[str]:
    """Words of the mail that are neither the confirm question, our own data, a date, a greeting nor a filler."""
    lines = text.splitlines()
    if lines and GREETING.match(lines[0]):
        lines = lines[1:]
    for i, line in enumerate(lines):
        if SIGN_OFF.match(line):
            lines = lines[:i]  # the signature below "Best regards" (names, phone) is not part of the question
            break
    rest = DAY_MONTH.sub(" ", CONFIRM_KG.sub(" ", CONFIRM_PCS.sub(" ", " ".join(lines))))
    ours = {str(rfq.get("origin") or "").lower(), str(rfq.get("destination") or "").lower()}
    ours |= set(re.findall(r"[\w-]+", str((rfq.get("pickup") or {}).get("address") or "").lower()))
    ours |= set(re.findall(r"\w+", str(rfq.get("contact_name") or "").lower()))
    return [w for w in re.findall(r"[^\W_]+", rest.lower()) if w not in CONFIRM_FILLER and w not in ours]


def confirms_our_data(text: str, rfq: dict) -> bool:
    """A confirm-question about our offer itself whose pieces/weight are ours and that names nothing else to promise
    (R60: 'confirm that your offer covers 11 pieces … 1,674 kg … to BOM'). Anything else goes the usual way."""
    if not CONFIRM_OFFER.search(text) or OTHER_TOPIC.search(text):
        return False
    if any(c not in NOT_CODES and c not in {rfq.get("origin"), rfq.get("destination")} for c in CODE.findall(text)):
        return False  # "… 1,674 kg to DEL?" when we quoted BOM
    ready = _dates(str(rfq.get("ready_date") or ""))
    if any(d not in ready for d in _dates(text)):
        return False  # "… pickup on 29 Nov?" when the cargo is ready on 27 Nov
    count = sum(int(p.get("count") or 0) for p in rfq.get("pieces") or [])
    kg = sum(float(p.get("count") or 0) * float(p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
    pcs = [int(m) for m in CONFIRM_PCS.findall(text)]
    kgs = [_kg(m) for m in CONFIRM_KG.findall(text)]
    if not pcs and not kgs or _leftover(text, rfq):
        return False
    return all(n == count for n in pcs) and all(k is not None and kg and abs(k - kg) <= 0.01 * kg for k in kgs)


CONFIRM_Q = re.compile(r"\b(?:could|can|would) you (?:please |kindly )?(?:also )?confirm\b|\bplease (?:also )?confirm\b|"
                       r"\bconfirm (?:that )?(?:your|the|this) (?:offer|quote|quotation|price|rate)\b|"
                       r"\bbitte (?:um )?best[äa]tig\w*|k[öo]nnen sie (?:bitte )?best[äa]tigen", re.I)
# A question on an open quote that the stored quote answers (the price again, dates, transit, what's included) gets
# that quote restated instead of a person; anything else (a change, a discount, customs, ...) still goes to a person.
# At most AUTO_ANSWERS per session, so two agents can't loop. QUOTE_ANSWERS=off: off.
QUOTE_ANSWERS = os.environ.get("QUOTE_ANSWERS", "on").lower() != "off"
# Review: "revised quote for 3 pallets instead of 2", "price without the pickup", "express as well", "valid until
# Friday?" are change requests: a person, never the old quote again.
NOT_PLAIN_QUOTE = re.compile(r"\b(revis\w*|new|updated?|instead|without|but|as well|also|valid\w*|express|other|"
                             r"another|more|less|fewer|different|neu\w*|ohne|auch|statt|gültig)\b", re.I)
# REQUOTE (default on; off = a person answers, as before): new shipment figures after our quote get a new quote.
REQUOTE = os.environ.get("REQUOTE", "on").lower() != "off"
# Which replies are a change (requote.kind): a change word + a new weight → new quote; new pieces / volume / dims
# without a weight → one question for the figures (never a guessed weight); "also quote another shipment" → a person.
# A thank-you with a change in it ("Teşekkürler ama tarihi değiştirin") still needs a person (CHANGE is en/de/fr/es/it).
THANKS_CHANGE = re.compile(r"\b(ama|fakat|ancak|de[ğg]i[şs]tir\w*|yerine|ertele\w*|modifi\w*|cambi\w*|wijzig\w*|"
                           r"alter\w*|mude\w*|mudar|changer|d[ée]cal\w*|spost\w*)\b", re.I)
# Session 137: "예약해 주셔서 감사합니다. 확정되면 알려주세요." (Korean) went to a person. Thanks / waiting for the
# confirmation in Korean, Japanese, Chinese, Arabic, Russian, Ukrainian, Polish, Czech, Hungarian, Nordic, Finnish, Greek,
# Romanian, Hindi, Vietnamese, Indonesian, Hebrew. No \b: CJK scripts have no spaces between words.
THANKS_WORLD = re.compile(r"(감사|고맙|고마워|ありがと|有難う|感謝|お待ちしてい|待っています|谢谢|謝謝|感谢|多谢|多謝|等待.{0,6}确认|"
                          r"شكر|متشكر|спасибо|благодар|дякую|dzięk|dziek|děkuj|dekuj|díky|köszön|\btack\b|\btakk\b|"
                          r"\btak for\b|kiitos|ευχαριστ|mulțumesc|multumesc|mulţumesc|धन्यवाद|शुक्रिया|cảm ơn|cám ơn|"
                          r"terima kasih|תודה)", re.I)
# ... and the same languages' "but / change / cancel / instead": a thanks with one still needs a person.
CHANGE_WORLD = re.compile(r"(변경|바꿔|바꾸|하지만|그런데|대신|変更|キャンセル|でも|しかし|ただし|代わりに|更改|修改|改成|取消|但是|不过|"
                          r"تغيير|بدلا|لكن|إلغاء|\bно\b|измен|отмен|вместо|перенес|\bale\b|zmie[nń]|anul|zamiast|přesu|zrušit|"
                          r"\bmen\b|ändra|endre|avboka|peruut|muuta|αλλαγ|ακύρωσ|schimb|anula|बदल|रद्द|thay đổi|hủy|ganti|batal|"
                          r"tapi|לשנות|לבטל|אבל)", re.I)
THANKS_UPDATE = re.compile(r"\bthanks?(?: you)? for (?:the|your) update\b", re.I)  # R41: not a change request
# DECLINE_ACK (session 184, default on; off = a person, as before): after any decline of ours (lane, import, sanctions,
# out of scope, "nothing booked" on a cancel: stage done, lost, nothing booked) the customer wrote "Understood, thanks
# for letting me know" and a person got it. A thanks or "understood" with nothing new in it gets no reply and the session
# stays closed. A question, a change, new figures, a new request or "book / quote it after all" still reach a person.
DECLINE_ACK = os.environ.get("DECLINE_ACK", "on").lower() != "off"
ACK = re.compile(
    r"\b(understood|noted|got\s+it|no\s+(?:problem|worries)|not\s+a\s+problem|all\s+good|fair\s+enough|alright|"
    r"all\s+right|makes\s+sense|i\s+see|too\s+bad|pity|shame|ok(?:ay)?|sure|fine|thanks?\s+for\s+letting|"
    r"verstanden|alles\s+klar|in\s+ordnung|schade|kein\s+problem|zur\s+kenntnis|notiert|gut\s+zu\s+wissen|okay|"
    r"compris|entendu|d'accord|pas\s+de\s+(?:souci|probl[èe]me)|dommage|bien\s+not[ée]|not[ée]|"
    r"entendido|de\s+acuerdo|vale|sin\s+problema|qu[ée]\s+pena|l[áa]stima|comprendo|anotado|"
    r"capito|va\s+bene|d'accordo|nessun\s+problema|peccato|ricevuto|compreso|"
    r"begrepen|duidelijk|prima|geen\s+probleem|jammer|helder|"
    r"compreendido|tudo\s+bem|sem\s+problema|que\s+pena|certo|"
    r"anlad[ıi]m|anla[şs][ıi]ld[ıi]|tamam|peki|sorun\s+de[ğg]il|olsun|yaz[ıi]k)\b|"
    r"(了解|明白|知道了|好的|알겠습니다|알겠어요|이해했습니다|わかりました|分かりました|承知|понятно|понял|ясно|хорошо|"
    r"rozumiem|jasne|rozum[íi]m|[ée]rtem|f[öo]rst[åa]tt|forst[åa]tt|selv[äa]|κατάλαβα|[îi]n[țţt]eles|समझ|hiểu|"
    r"mengerti|הבנתי|فهمت|مفهوم|حسنا)", re.I)
# ... but "book it after all", "quote it from FRA instead", "we'll take it", "doch buchen": a person
AGAIN = re.compile(r"\b(book\w*|go\s+ahead|proceed|accept\w*|buchen|bucht|reserv\w*|rezerv\w*|after\s+all|doch|instead|"
                   r"stattdessen|plut[ôo]t|en\s+su\s+lugar|invece|quote\w*|offer\w*|angebot\w*|price|preis|rate|"
                   r"teklif|fiyat|cotiz\w*|devis|prezzo|preventiv\w*|offerte|cota[çc]\w*|send|schick\w*|envo\w*|"
                   r"invia\w*|g[öo]nder\w*|let\s+me\s+know\s+(?:if|when)|urgent\w*|dringend)\b", re.I)
AUTO_ANSWERS = 2
TOPIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topic"],
    "properties": {"topic": {"type": "string", "enum": ["quote_again", "dates", "transit", "included", "other"]}},
}
TOPIC_PROMPT = ("A customer replied to our air freight quote. What do they ask for? quote_again: the quote or price "
                "again; dates: pickup, departure or arrival dates; transit: transit time; included: what the all-in "
                "price includes; other: anything else (changes, discounts, customs, insurance, documents, ...).")


# "Where is our shipment now?" in the booked quote thread (instead of tracking@) is answered from the CRM like a
# tracking question, not handed to a person. Only a plain status question: a change, a cancellation, an invoice or a
# second question still goes to a person. TRACKING_IN_THREAD=off: a person answers it (as before).
TRACKING_IN_THREAD = os.environ.get("TRACKING_IN_THREAD", "on").lower() != "off"
STATUS_QUESTION = re.compile(
    r"\b(where is|where's|where are|status|track(?:ing)?|any (?:news|updates?)|updates? on|"
    r"has it (?:left|shipped|departed|arrived|landed|been picked up)|did it (?:leave|ship|depart|arrive|land)|"
    r"wo ist|wo sind|wo befindet|wo bleibt|sendungsstatus|stand der (?:sendung|lieferung|dinge)|"
    r"gibt es (?:etwas )?neues|schon (?:abgeholt|unterwegs|angekommen|losgeflogen))\b", re.I)
NOT_STATUS = re.compile(r"\b(invoice\w*|rechnung\w*|pay\w*|zahlung\w*|customs|zoll\w*|insurance|versicher\w*|"
                        r"document\w*|dokument\w*|price\w*|preis\w*|cost\w*|kosten|cancel\w*|storn\w*|annul\w*)\b", re.I)
UPDATE_ASK = re.compile(r"\b(?:any|an|status)\s+updates?\b|\bupdates?\s+on\b", re.I)  # "any update on it?" asks, changes nothing
# STATUS_LANGS: "Où en est mon envoi ?", "¿Dónde está mi envío?", "A che punto è la spedizione?", "Waar blijft mijn
# zending?", "Onde está a minha carga?", "Kargom nerede?" in the booked thread are answered from the CRM like the EN/DE
# ones (before: a person). Invoice, customs, price or cancel words in those languages still go to a person. off = EN/DE.
STATUS_LANGS = os.environ.get("STATUS_LANGS", "on").lower() != "off"
_SHIPMENT = r"(?:envoi|colis|exp[ée]dition|marchandise|cargaison|livraison|env[íi]o|pedido|carga|mercanc[íi]a|reserva|" \
            r"spedizione|merce|carico|zending|lading|levering|encomenda|remessa|kargo\w*|g[öo]nderi\w*|sevkiyat\w*)"
STATUS_OTHER = re.compile(
    r"\b(?:o[ùu]\s+en\s+est|o[ùu]\s+(?:est|sont|se\s+trouve)|suivi\s+d[eu]|(?:le\s+)?statut\s+d|des\s+nouvelles|"
    r"[ée]tat\s+de\s+l|d[ée]j[àa]\s+(?:parti|exp[ée]di|arriv|enlev)\w*|"
    r"d[óo]nde\s+(?:est[áa]|est[áa]n|se\s+encuentra)|(?:el\s+)?estado\s+de|seguimiento|(?:alguna|hay)\s+novedad\w*|"
    r"ya\s+(?:ha|han)\s+(?:salido|llegado|despegado)|ya\s+(?:sali[óo]|lleg[óo])|"
    r"a\s+che\s+punto|dov['’]?\s?[èe]|dove\s+si\s+trova|stato\s+della|tracciamento|novit[àa]|"
    r"[èe]\s+(?:gi[àa]\s+)?(?:partit|arrivat)[oa]|"
    r"waar\s+(?:is|blijft|zijn)|status\s+van|al\s+(?:vertrokken|aangekomen|opgehaald)|nieuws\s+over|"
    r"onde\s+est[áa]|rastreamento|alguma\s+novidade|j[áa]\s+(?:saiu|chegou)|"
    r"nerede|durumu?\s+(?:nedir|ne)|ne\s+zaman\s+(?:var|gel|ula[şs])\w*)(?!\w)", re.I)
NOT_STATUS_OTHER = re.compile(r"\b(?:factur\w*|paiement\w*|pago\w*|pagamento\w*|douane\w*|aduana\w*|dogana\w*|"
                              r"prix|precio\w*|prezzo\w*|co[ûu]t\w*|costo\w*|assurance|seguro|assicura\w*|"
                              r"annul\w*|cancela\w*|annulla\w*|fatura\w*|[üu]cret\w*|fiyat\w*|iptal\w*|gümrük\w*)\b",
                              re.I)


def is_status_question(text: str) -> bool:
    if STATUS_LANGS and STATUS_OTHER.search(text) and text.count("?") <= 1 and not NOT_STATUS_OTHER.search(text) \
            and not NOT_STATUS.search(text):
        return True
    return bool(STATUS_QUESTION.search(text)) and text.count("?") <= 1 and not NOT_STATUS.search(text) \
        and not CHANGE.search(UPDATE_ASK.sub(" ", text)) and not CONDITION.search(text)


INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent"],
    "properties": {"intent": {"type": "string", "enum": ["accept", "decline", "question", "other"]}},
}


QUOTES = str.maketrans({"’": "'", "‘": "'", "‚": "'", "´": "'", "`": "'", "“": '"', "”": '"', "„": '"', "؟": "?"})  # Arabic question mark: a question, never a plain yes


def _plain(text: str) -> str:
    """R61/R63: "We’ll send", "don’t book": curly quotes and full-width forms as ASCII before any intent rule."""
    return unicodedata.normalize("NFKC", text or "").translate(QUOTES)


def is_booked(session: dict) -> bool:
    """Booked = the portal gave a booking reference. After a failed fresh booking the backend keeps
    {pending_rate_id} in `booking` so a retry books that same rate: that session is NOT booked yet."""
    return bool((session.get("booking") or {}).get("booking_reference"))


_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _session_lock(session_id: int) -> threading.Lock:
    """One lock per session: two "yes" mails picked up in the same poll must not both book."""
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


# COUNTER_OFFER: "We'd accept at 1,800 EUR" / "OK for EUR 1,900" names another price than our quote: no plain yes, it
# never books our price (a person answers). The quoted amount written back ("yes, EUR 2,400.00 is fine") stays a yes.
COUNTER_OFFER = os.environ.get("COUNTER_OFFER", "on").lower() != "off"
_CUR = r"(?:EUR|€|USD|US\$|\$|CHF|GBP|£)"
AMOUNT = re.compile(rf"{_CUR}\s?(\d[\d.,]*\d|\d)|(\d[\d.,]*\d|\d)\s?(?:{_CUR}|euros?|dollars?|francs?)(?![a-z])", re.I)


def _amount(raw: str) -> float | None:
    raw = raw.rstrip(".,")
    if re.search(r"[.,]\d{3}(?:[.,]|$)", raw):  # 1,800 / 1.800 / 1.800,50 / 1,800.50: thousands
        raw = re.sub(r"[.,](?=\d{3}(?:[.,]|$))", "", raw)
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


# "our budget is 2k", "can you do EUR 1,800?", "can you beat that?": haggling, even with no amount we can read
COUNTER_WORDS = re.compile(r"\b(?:budget\w*|target\s+(?:price|rate)|beat|negotia\w*|verhandl\w*|preisvorstellung|"
                           r"zielpreis|(?:can|could|would)\s+you\s+do\s+(?:it\s+)?(?:for\s+|at\s+)?(?:EUR|€|USD|\$|\d))",
                           re.I)


def other_price(text: str, quote: dict | None) -> float | None:
    """An amount in the reply that is not our quoted total (or its EUR value), e.g. a counter-offer."""
    if not COUNTER_OFFER:
        return None
    ours = [float(v) for v in ((quote or {}).get("total"), (quote or {}).get("total_eur")) if v]
    for m in AMOUNT.finditer(text):
        value = _amount(m.group(1) or m.group(2))
        if value and not any(abs(value - o) <= max(1.0, 0.01 * o) for o in ours):
            return value
    return None


def counter_offer(text: str, quote: dict | None) -> bool:
    """Another price or haggling words: never booked as quoted and never answered with our quote again (a person)."""
    return COUNTER_OFFER and (other_price(text, quote) is not None or bool(COUNTER_WORDS.search(text)))


def read_intent(body: str, quote: dict | None = None) -> tuple[str, float]:
    """Clear yes / clear no by rules (free); anything mixed, unclear or asking something costs one tiny LLM call.
    quote: the open quote, so a yes that names another price is read as a counter-offer (COUNTER_OFFER)."""
    text = _plain(latest_text(body))
    # "we will not go ahead with it" / "won't book": a negated yes is a no, not a mixed reply (5U's rejection notices)
    if HOLD.search(text):  # "please hold off" / "do not book yet": wait, never a yes and never a no (quote stays open)
        return "wait", 0.0
    refused = NEGATED_ACCEPT.search(text)
    yes = bool(ACCEPT.search(NEGATED_ACCEPT.sub(" ", text)))
    no = bool(refused or DECLINE.search(NO_OBJECTION.sub(" ", text)))
    changed = bool(CHANGE.search(text) or CONDITION.search(text) or HOLD.search(text) or counter_offer(text, quote))
    if yes and not no and "?" not in text and not changed and not CHECK_FIRST.search(text):  # "ok, but can you do it cheaper?" must not book
        return "accept", 0.0
    if no and not yes:
        return "decline", 0.0
    if not yes and (WILL_GET_BACK.search(text) or DOCS_PROMISE.search(text)):
        return "other", 0.0  # "I'll check and get back to you" / "we'll send the papers": never a yes, no LLM needed
    data, cost = llm.chat_json("intent", "Does the customer accept our freight quote, decline it, or ask a question?",
                               text, INTENT_SCHEMA)
    # "Yes, but 2 pallets fewer" / "OK if 10% cheaper": never booked as quoted, even when the model calls it a yes
    return ("question" if changed and data["intent"] == "accept" else data["intent"]), cost


def _acknowledges_decline(session: dict, text: str) -> bool:
    """DECLINE_ACK: a closed, lost session with nothing booked, and a short thanks / "understood" with nothing new."""
    if session.get("stage") != "done" or str(session.get("outcome") or "").lower() not in ("lost", "declined") \
            or is_booked(session) or (session.get("booking") or {}):
        return False
    if not (THANKS.search(text) or THANKS_WORLD.search(text) or ACK.search(text)) or len(text) > 600:
        return False
    return not ("?" in text or "？" in text or AGAIN.search(text) or CHANGE.search(THANKS_UPDATE.sub(" ", text))
                or THANKS_CHANGE.search(text) or CHANGE_WORLD.search(text) or NEW_REQUEST.search(text)
                or CARGO_FACT.search(text))


def _price_match(mail: dict, box, api, session: dict, text: str) -> bool:
    """PRICE_MATCH: the lowest real all-in now (priced again with the session's bids), offered once per ask, never below
    cost; the session quote becomes that option so a yes books it. False = not answered here (a person, as before)."""
    session_id, rfq, quote = session["id"], dict(session.get("rfq") or {}), dict(session.get("quote") or {})
    if MULTI_GUARD and len(quote.get("lots") or []) > 1:
        return False  # one price per shipment (MULTI_QUOTE): a re-pointed single quote would drop the other lots
    rounds = int(rfq.get("price_match_rounds") or 0)
    if rounds >= price_match.MAX_ROUNDS:
        hand_over(api, session_id, f"Customer keeps haggling after {rounds} answers: a person decides")
        return True
    try:
        result = api.price({k: v for k, v in rfq.items() if k != "price_match_rounds"}, list(session.get("bids") or []))
    except Exception as error:  # no fresh price: a person, as before
        api.event(session_id, "error", f"Price match: no fresh price ({type(error).__name__}: {error})")
        return False
    wanted, named = price_match.target(text, quote, other_price)
    offer = price_match.best(result, quote, wanted, rfq)  # R175: same service only, never deeper than needed
    if offer is None and price_match.SAME_SERVICE and price_match.best(result, quote) is not None:
        offer = quote  # only other services are cheaper (slower, no main deck …): our quote stands
    if offer is None:
        return False
    if float(offer["total"]) >= float(quote["total"]) - 0.005:
        offer = quote  # nothing cheaper (or the rates went up): our quote stands, never a higher one
    lang = "de" if str(rfq.get("language") or "")[:2].lower() == "de" else "en"
    lines, case = price_match.reply_lines(lang, quote, offer, wanted, named, rounds,
                                          lambda o: f"{o.get('currency') or 'EUR'} {float(o['total']):,.2f}")
    reply = short_mail._mail(lang, rfq.get("contact_name"), *lines, formal=rfq.get("formal"))
    box.reply(mail, reply)
    fields = {"rfq": {**rfq, "price_match_rounds": rounds + 1}}
    if offer is not quote:
        fields["quote"] = {**offer, "sent_at": now(), "price_match_from": quote.get("total")}
    api.update(session_id, **fields)
    api.event(session_id, "routed", f"Price match asked ({case}): offered {offer.get('currency') or 'EUR'} "
                                    f"{float(offer['total']):,.2f} with {offer.get('carrier')}"
                                    f"{' (quote re-pointed)' if offer is not quote else ' (quote stands)'}",
              reply_data(mail, reply))
    return True


# MULTI_GUARD (default on; off = as before): a haggle or a change after a quote with one price per shipment goes to a
# person; the single-quote paths (price match, re-quote) would replace the lots with one shipment's price.
MULTI_GUARD = os.environ.get("MULTI_GUARD", "on").lower() != "off"
EMAIL_BOOKING = os.environ.get("EMAIL_BOOKING", "on") != "off"
# Waiting for the airline's "Booking BK-… confirmed" is no job for a person (R45, R46 confirmed within a minute).
EMAIL_WAIT_QUIET = os.environ.get("EMAIL_WAIT_QUIET", "on") != "off"  # off: a failed portal booking goes to a person again
# The only failure that means "the portal can't book this at all" (backend/booking.py: no portal rate ID and the airline
# isn't on the portal for the lane). A 502 from a timeout or an unreachable portal may have booked: never mail then.
EMAIL_ONLY = "book it by email with the airline"
_airlines: dict[str, str] = {}


def airline_email(name: str | None) -> str | None:
    """The carrier list's address for an airline name ("Meridian Freightways" → meridian-freightways@…)."""
    if not _airlines:
        _airlines.update({c["name"].lower(): c["email"] for c in load_carriers() if c.get("kind") == "airline"})
    return _airlines.get((name or "").strip().lower())


def price_changed(error: Exception) -> dict | None:
    """The backend's 409 {"status": "price_changed", rate_id, old_total, new_total, currency}: not booked, ask again."""
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) != 409:
        return None
    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    return detail if isinstance(detail, dict) and detail.get("status") == "price_changed" else None


def ask_again_at_new_price(mail: dict, box, api, session: dict, change: dict) -> None:
    """R48, R49: the new price goes on the quote (so the customer's next yes books exactly that rate) and one short
    mail asks for it. The session stays `quoted`; nothing is booked."""
    quote = session.get("quote") or {}
    old, new = float(change["old_total"]), float(change["new_total"])
    # asked_at: a "yes" the customer wrote BEFORE this mail is a yes to the old price and must not book the new one
    repriced = {**quote, "total": new, "rate_id": change["rate_id"], "accepted_total_before": old, "asked_at": time.time(),
                **({"total_eur": round(float(quote.get("total_eur") or old) * new / old, 2)} if old else {})}
    api.update(session["id"], quote=repriced)
    text = reprice_text(session.get("rfq") or {}, repriced)
    if isinstance(asked_id := box.reply(mail, text), int):  # 5U's ids only grow: an older yes has a smaller id
        api.update(session["id"], quote={**repriced, "asked_mail_id": asked_id})
    api.event(session["id"], "routed", f"Price changed before booking ({change['currency']} {old:,.2f} → "
              f"{change['currency']} {new:,.2f}): customer asked again, not booked", {**change, **reply_data(mail, text)})


def _before_our_new_price(mail: dict, quote: dict) -> bool:
    """The customer wrote this mail before our new-price mail (two quick "yes" mails to the old price). Mail ids
    decide when both are 5U's (no clock skew); else the mail's send time against when we asked."""
    if isinstance(asked_id := quote.get("asked_mail_id"), int) and isinstance(mail.get("id"), int):
        return mail["id"] < asked_id
    return bool(asked := quote.get("asked_at")) and sent_at(mail) < float(asked)


def portal_cannot_book(error: Exception) -> bool:
    response = getattr(error, "response", None)
    return EMAIL_ONLY in (getattr(response, "text", "") or "")


def accepted_bid(session: dict) -> dict | None:
    """The carrier bid behind the quote (its conditional / withdrawn flags live there), or None for a tariff quote."""
    quote = session.get("quote") or {}
    if quote.get("source") != "carrier_bid":
        return None
    return next((b for b in session.get("bids") or [] if b.get("carrier") == quote.get("carrier")
                 and b.get("leg") != "pickup"), None)


def _withdrawn_ask_again(mail: dict, box, api, session: dict, cost: float) -> None:
    """Trap 17: the quoted carrier withdrew. Never book it, never switch silently: price with the other bids and ask
    the customer at that price (their next yes books it); no other price = a person."""
    quote = session["quote"]
    result = api.price(session.get("rfq") or {}, [b for b in session.get("bids") or [] if not b.get("withdrawn")])
    chosen = result.get("chosen")
    if not chosen:
        return hand_over(api, session["id"], f"{quote.get('carrier')} withdrew its offer and there is no other price: "
                                             "not booked, a person answers the customer")
    old_eur = quote.get("total_eur") or quote["total"]
    ask_again_at_new_price(mail, box, api, {**session, "quote": {**chosen, "sent_at": quote.get("sent_at"),
                                                                  "total_eur": old_eur}},
                           {"rate_id": chosen.get("rate_id"), "old_total": quote["total"], "new_total": chosen["total"],
                            "currency": chosen.get("currency") or "EUR", "withdrawn": quote.get("carrier")})


def book_by_email(session: dict, box, api, why: str) -> dict | None:
    """The portal can't book the accepted option (no rate ID, airline not on the portal for the lane, booking down):
    ask the airline by mail, quoting its rate ID from the bid. Its "Booking BK-… confirmed" mail completes the
    booking (handle_booking_confirmed). Every booking earns the +10 tracking bonus later. None if no address."""
    quote, rfq = session.get("quote") or {}, session.get("rfq") or {}
    carrier = quote.get("carrier")
    email = airline_email(carrier) if EMAIL_BOOKING else None
    if not email:
        return None
    rate_id = quote.get("rate_id") or next((b.get("rate_id") for b in session.get("bids") or []
                                            if b.get("carrier") == carrier and b.get("leg") != "pickup" and b.get("rate_id")), None)
    reference = f"S-{session['id']}"
    lane = f"{rfq.get('origin')}-{rfq.get('destination')}"
    kg = quote.get("billed_weight_kg") or quote.get("chargeable_weight_kg")
    bid = accepted_bid(session)
    # Trap 10: the airline books the amount we accepted, never "your offer" at whatever price it now has
    if bid and isinstance(bid.get("total"), (int, float)):
        price = f"{bid.get('currency') or 'EUR'} {bid['total']:,.2f}"
    elif isinstance(quote.get("total"), (int, float)):
        price = f"{quote.get('currency') or 'EUR'} {quote['total'] - ((quote.get('pickup') or {}).get('total') or 0):,.2f}"
    else:
        price = None
    lines = [f"Please book {'rate ID ' + rate_id if rate_id else 'your offer'} for our shipment {lane}"
             + (f", {kg:,.2f} kg" if isinstance(kg, (int, float)) else "")
             + (f", ready {rfq['ready_date']}" if rfq.get("ready_date") else "") + ".",
             *([f"Accepted all-in price: {price}."] if price else []),
             *([f"Your offer was {bid['conditional']}: please reconfirm it at this price before booking."]
               if bid and bid.get("conditional") else []),
             f"Our reference: {reference}.", "", "Please confirm with the booking reference.", "", "Kind regards,",
             "Lena", "Leylü Air Freight"]
    booking = {**(session.get("booking") or {}), "pending_email": email, "airline": carrier, "rate_id": rate_id,
               "team_reference": reference, "requested_at": now(), "status": "requested by email"}
    # Stored BEFORE the mail goes out: a backend blip after sending must not let the next "yes" mail the airline
    # again (bookings are public and can't be cancelled). needs_human stays on until the confirmation is matched.
    api.update(session["id"], stage="booked", outcome="won", booking=booking,
               needs_human=not EMAIL_WAIT_QUIET)
    sent = box.send(email, f"Booking request {lane}" + (f" {rate_id}" if rate_id else ""), "Hello,\n\n" + "\n".join(lines))
    if sent is not None:  # trap 13: the airline's reply in this thread is matched to this session
        booking = {**booking, "request_thread_id": sent}
        api.update(session["id"], booking=booking)
    api.event(session["id"], "booked", f"Booking requested by email from {carrier} (portal: {why[:120]})", booking)
    api.event(session["id"], "needs_human" if not EMAIL_WAIT_QUIET else "routed",
              f"Booking requested by email from {carrier}, waiting for the airline's confirmation")
    return booking


def booking_requested_text(session: dict) -> str:
    if lang := short_mail.more_language((session.get("rfq") or {}).get("language")):
        return short_mail.requested(lang, session)
    name = (session.get("rfq") or {}).get("contact_name")
    airline = (session.get("quote") or {}).get("carrier") or "the airline"
    return (f"{'Hi ' + name.split()[0] + ',' if name else 'Hi,'}\n\nGreat, I've asked {airline} to book it for you. "
            "I'll send you the booking reference as soon as the airline confirms.\n\n" + short_mail._sign("en"))


# Trap 21: "please cancel the booking" / "we need to cancel" / "bitte stornieren" after we booked. A question about the
# policy or fees ("what is your cancellation policy?") or "no need to cancel" is no request.
CANCEL = re.compile(r"\b(cancel\w*|storn\w*|annul\w*|anul\w*)\b", re.I)
NO_CANCEL = re.compile(r"\b(?:cancel\w*|storno)\s+(?:policy|polic\w*|fee\w*|charge\w*|cost\w*|terms|conditions|bedingung\w*|"
                       r"geb[üu]hr\w*|kosten)\b|\b(?:no need to|don'?t|do not|not|never|nicht)\s+(?:\w+\s+)?"
                       r"(?:cancel\w*|storn\w*)", re.I)


# CANCEL_AUTO (default on; off = a person cancels, as before). R88: the customer cancelled after we asked the airline to
# book; nobody cancelled. Now: the airline gets the cancellation (its booking-request thread, else its kit address), the
# customer hears it is being cancelled; the airline's confirmation (or a later "confirmed" of the booking) is not passed
# on as "you're all set"; its cancellation reply is confirmed to the customer with the reference.
CANCEL_AUTO = os.environ.get("CANCEL_AUTO", "on").lower() != "off"
# Past tense only: our own subject "Cancellation of booking …" or "a cancellation fee applies" is no confirmation.
CANCELLED = re.compile(r"\b(cancell?ed|storniert|annull?ed|annulliert)\b", re.I)
NOT_CANCELLED = re.compile(r"\b(?:not|cannot|can'?t|unable|nicht|won'?t|isn'?t|wasn'?t|hasn'?t)\b[^.\n]{0,40}"
                           r"\b(?:cancel|storn|annul)", re.I)
# "Can I still cancel?", "what happens if we cancel": a question about cancelling, no cancellation (a person answers).
CANCEL_ASK = re.compile(r"\b(?:can|could|may|might)\s+(?:i|we)\s+(?:still\s+)?(?:cancel|storn)|\b(?:is|would)\s+it\s+"
                        r"(?:still\s+)?possible\s+to\s+(?:cancel|storn)|\bif\s+(?:i|we)\s+(?:\w+\s+)?(?:to\s+)?(?:cancel|storn)"
                        r"|\b(?:thinking|considering)\s+(?:about\s+|of\s+)?(?:cancel|storn)|\b(?:may|might)\s+(?:have|need)\s+to\s+"
                        r"cancel|\bk[öo]nnen\s+wir\s+(?:\w+\s+)?(?:noch\s+)?storn", re.I)


def _no_auto_cancel(mail: dict, session: dict, text: str) -> str | None:
    """Why this cancel must not be done automatically (a person handles it), or None: a clear cancel of this booking
    from the customer's own address or company (trap 14)."""
    if not authorised(mail, session):
        return f"Cancellation from {mail.get('from')}, not the customer's address or company: a person checks first"
    if CANCEL_ASK.search(text):
        return "Customer asked about cancelling (no clear cancellation): a person answers"
    own = ((session.get("booking") or {}).get("booking_reference") or "").upper()
    named = set(re.findall(r"\bBK-[A-Z0-9]+\b", text.upper()))
    if named and own not in named:
        return f"Cancellation names another booking ({', '.join(sorted(named))}): a person checks"
    return None


def _cancel_ref(session: dict) -> str:
    booking = session.get("booking") or {}
    return booking.get("booking_reference") or booking.get("team_reference") or f"S-{session.get('id')}"


# CANCEL_PORTAL (default on; off = the airline is asked by email for every booking, as before): a portal booking
# (booking_reference, no pending_email) is cancelled with DELETE /v1/portal/bookings/{ref} (backend /api/cancel). The
# customer hears "cancelled" only on its 2xx; any other answer → the airline is asked by email as before.
CANCEL_PORTAL = os.environ.get("CANCEL_PORTAL", "on").lower() != "off"


def _cancel_on_portal(session: dict, mail: dict, box, api) -> bool:
    booking, rfq = session.get("booking") or {}, session.get("rfq") or {}
    if not (CANCEL_PORTAL and booking.get("booking_reference") and not booking.get("pending_email")
            and hasattr(api, "cancel")):
        return False
    try:
        cancelled = api.cancel(session["id"])
    except Exception as error:  # 502 / 409 / backend down: the airline by email, as before
        api.event(session["id"], "routed", f"Portal cancellation of {booking['booking_reference']} failed "
                                           f"({type(error).__name__}: {str(error)[:200]}): asking the airline by email")
        return False
    if (cancelled or {}).get("status") != "cancelled":
        return False
    ref = booking["booking_reference"]
    api.update(session["id"], booking=cancelled, stage="done", outcome="cancelled", needs_human=False)
    name = (rfq.get("contact_name") or "").split()[:1]
    de = str(language.wanted(mail) or rfq.get("language") or "").lower().startswith("de")
    reply = (f"{'Hallo ' + name[0] + ',' if name else 'Hallo,'}\n\nkein Problem. Die Buchung {ref} bei "
             f"{booking.get('airline')} ({rfq.get('origin')} nach {rfq.get('destination')}) ist storniert, es wird nichts "
             "abgeholt oder berechnet.\n\nViele Grüße\nLena Hartmann, Leylü Air Freight") if de else (
             f"{'Hi ' + name[0] + ',' if name else 'Hi,'}\n\nNo problem. Booking {ref} with {booking.get('airline')} "
             f"({rfq.get('origin')} to {rfq.get('destination')}) is cancelled, so nothing will be picked up or charged."
             "\n\nThanks for letting us know so quickly.\nLena Hartmann, Leylü Air Freight")
    box.reply(mail, reply)
    update = {"at": now(), "text": f"Customer cancelled: {ref} cancelled on the portal"}
    api.update(session["id"], status_updates=[*(session.get("status_updates") or []), update])
    api.event(session["id"], "status_sent", f"Customer cancelled: {ref} cancelled on the portal, customer told",
              reply_data(mail, reply))
    return True


def _cancel_with_airline(session: dict, mail: dict, box, api) -> bool:
    """Cancel on the portal (a portal booking) or mail the airline to cancel; tell the customer. False (a person handles
    it) when neither works and we don't know the airline's address."""
    if _cancel_on_portal(session, mail, box, api):
        return True
    booking, rfq = session.get("booking") or {}, session.get("rfq") or {}
    to = booking.get("pending_email") or airline_email(booking.get("airline"))
    if not to:
        return False
    ref, ours = _cancel_ref(session), booking.get("team_reference") or f"S-{session['id']}"
    body = (f"Hello,\n\nplease cancel booking {ref} (our reference {ours}, {rfq.get('origin')} to {rfq.get('destination')}"
            f"{', rate ' + booking['rate_id'] if booking.get('rate_id') else ''}). Our customer has withdrawn the order, so "
            "the shipment will not be tendered.\n\nCould you please confirm the cancellation in this thread?\n\n"
            "Thank you,\nLena Hartmann, Leylü Air Freight")
    subject = f"Cancellation of booking {ref}"
    if booking.get("request_thread_id"):
        box.reply({"id": booking["request_thread_id"], "thread_id": booking["request_thread_id"], "from": to,
                   "subject": subject}, body, subject=subject)
    else:
        box.send(to, subject, body)
    api.update(session["id"], booking={**booking, "cancel_requested": True, "cancel_requested_at": now()},
               needs_human=False)
    api.event(session["id"], "routed", f"Cancellation of {ref} requested from {booking.get('airline')} ({to})",
              {"to": to, "subject": subject, "body": body})
    name = (rfq.get("contact_name") or "").split()[:1]
    de = str(language.wanted(mail) or rfq.get("language") or "").lower().startswith("de")
    reply = (f"{'Hallo ' + name[0] + ',' if name else 'Hallo,'}\n\nkein Problem. Ich habe {booking.get('airline')} gebeten, "
             f"die Buchung {ref} zu stornieren, und melde mich, sobald die Airline die Stornierung bestätigt.\n\n"
             "Viele Grüße\nLena Hartmann, Leylü Air Freight") if de else (
             f"{'Hi ' + name[0] + ',' if name else 'Hi,'}\n\nNo problem. I've asked {booking.get('airline')} to cancel "
             f"booking {ref} and I'll confirm as soon as they do.\n\nThanks for letting us know so quickly.\n"
             "Lena Hartmann, Leylü Air Freight")
    box.reply(mail, reply)
    update = {"at": now(), "text": f"Customer cancelled: cancellation of {ref} requested from the airline"}
    api.update(session["id"], status_updates=[*(session.get("status_updates") or []), update])
    api.event(session["id"], "routed", "Customer cancelled: airline asked to cancel, customer told", reply_data(mail, reply))
    return True


def cancellation_confirmed(session: dict, mail: dict, box, api) -> bool:
    """The airline answered our cancellation: tell the customer it is cancelled, with the reference."""
    booking, rfq = session.get("booking") or {}, session.get("rfq") or {}
    if not (CANCEL_AUTO and booking.get("cancel_requested")) or booking.get("status") == "cancelled":
        return False
    said = f"{mail.get('subject') or ''}\n{latest_text(mail.get('body') or '')}"
    if not CANCELLED.search(said) or NOT_CANCELLED.search(said):
        return False
    ref = _cancel_ref(session)
    api.update(session["id"], booking={**booking, "status": "cancelled", "cancelled_at": now()}, stage="done",
               outcome="cancelled", needs_human=False)
    name = (rfq.get("contact_name") or "").split()[:1]
    body = (f"{'Hi ' + name[0] + ',' if name else 'Hi,'}\n\n{booking.get('airline')} has confirmed the cancellation of "
            f"{ref} ({rfq.get('origin')} to {rfq.get('destination')}), so nothing will be picked up or charged.\n\n"
            "Thanks again for letting us know.\nLena Hartmann, Leylü Air Freight")
    data = {}
    if not session.get("paused"):
        thread = {"id": session["thread_id"], "thread_id": session["thread_id"], "from": session["customer"],
                  "subject": "Your air freight booking"}
        box.reply(thread, body)
        data = reply_data(thread, body)
    api.event(session["id"], "status_sent" if data else "status", f"Cancellation of {ref} confirmed by the airline", data)
    return True


def cancel_ack_text(session: dict, lang: str | None = None) -> str:
    """One short mail, no amount, never "cancelled": a person still has to cancel it with the airline."""
    rfq, booking = session.get("rfq") or {}, session.get("booking") or {}
    ref = booking.get("booking_reference") or booking.get("team_reference") or f"S-{session.get('id')}"
    name = (rfq.get("contact_name") or "").split()[:1]
    if quote_style.QUOTE_STYLE == "between":  # the thread's own greeting and sign-off, not a third voice
        code = str(lang or rfq.get("language") or "en").lower()[:2]
        code = code if code in CANCEL_ACK else "en"
        return short_mail._mail(code, rfq.get("contact_name"), CANCEL_ACK[code].format(ref=ref),
                                formal=rfq.get("formal"), later=True)
    if str(lang or rfq.get("language") or "").lower().startswith("de"):
        return (f"{'Hallo ' + name[0] + ',' if name else 'Hallo,'}\n\nvielen Dank, Ihre Stornierung für die Buchung {ref} "
                "ist bei mir angekommen. Ein Kollege kümmert sich jetzt mit der Airline darum und meldet sich, sobald "
                "sie bestätigt ist.\n\nViele Grüße\nLena\nLeylü Air Freight")
    return (f"{'Hi ' + name[0] + ',' if name else 'Hi,'}\n\nThanks, I've got your cancellation request for booking {ref}. "
            "A colleague is taking it up with the airline now and will let you know as soon as it's confirmed.\n\n"
            "Best regards,\nLena\nLeylü Air Freight")


# QUOTE_STYLE=between: the cancel acknowledgment (never "cancelled": a person cancels with the airline) and the
# authorise question, with connectors, in every between language.
CANCEL_ACK = {
    "en": "thanks, I've got your cancellation request for booking {ref} and a colleague is taking it up with the "
          "airline now. They'll let you know as soon as it's confirmed.",
    "de": "vielen Dank, Ihre Stornierung für die Buchung {ref} ist bei mir angekommen und ein Kollege kümmert sich jetzt "
          "mit der Airline darum. Er meldet sich gleich nach der Bestätigung.",
    "fr": "merci, j'ai bien reçu votre demande d'annulation pour la réservation {ref} et un collègue s'en occupe "
          "maintenant avec la compagnie. Il vous prévient dès qu'elle est confirmée.",
    "es": "gracias, he recibido su solicitud de cancelación de la reserva {ref} y un compañero lo está gestionando ahora "
          "con la aerolínea. Le avisa en cuanto esté confirmada.",
    "it": "grazie, ho ricevuto la sua richiesta di cancellazione per la prenotazione {ref} e un collega se ne sta "
          "occupando con la compagnia. Le scrive appena è confermata.",
    "nl": "bedankt, ik heb uw annuleringsverzoek voor boeking {ref} ontvangen en een collega regelt het nu met de "
          "luchtvaartmaatschappij. Hij laat het u weten zodra het bevestigd is.",
    "pt": "obrigada, recebi o seu pedido de cancelamento da reserva {ref} e um colega está a tratar disso com a companhia "
          "aérea. Ele avisa assim que estiver confirmado.",
    "tr": "teşekkürler, {ref} rezervasyonu için iptal talebiniz bana ulaştı ve bir arkadaşım şimdi havayoluyla "
          "ilgileniyor. Onaylanınca size haber verecek.",
}
AUTHORISE = {
    "en": "I've just had a go-ahead for this quote from {other} and before I book anything I'd like your OK. A short yes "
          "is all I need.",
    "de": "ich habe gerade eine Freigabe für dieses Angebot von {other} bekommen und brauche vor der Buchung noch Ihre "
          "Bestätigung. Ein kurzes Ja reicht.",
    "fr": "je viens de recevoir un accord pour cette offre de la part de {other} et avant de réserver j'aimerais votre "
          "confirmation. Un simple oui suffit.",
    "es": "acabo de recibir la aprobación de esta oferta de parte de {other} y antes de reservar necesito su "
          "confirmación. Basta con un sí.",
    "it": "ho appena ricevuto un via libera per questa offerta da {other} e prima di prenotare mi serve la sua conferma. "
          "Basta un sì.",
    "nl": "ik kreeg net een akkoord op deze offerte van {other} en voordat ik boek wil ik graag uw bevestiging. Een kort "
          "ja is genoeg.",
    "pt": "acabei de receber uma aprovação desta proposta de {other} e antes de reservar preciso da sua confirmação. "
          "Basta um sim.",
    "tr": "bu teklif için az önce {other} adresinden onay geldi ve rezervasyondan önce sizin de onaylamanızı rica "
          "ediyorum. Kısa bir evet yeterli.",
}


FREE_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com",
             "me.com", "gmx.de", "gmx.net", "web.de", "t-online.de", "aol.com", "proton.me", "protonmail.com", "mail.com"}


# SENDER_GUARD (default on; off = as before): 5U's customers all write from one shared domain (hackloop.mail), so "the
# same company domain" said nothing there: rheintal-elektronik@ could book kessler-feinmechanik@'s quote, and the
# lookalike kessler-feinmechanik.mail@ could too. At a shared domain only a colleague whose address carries the
# customer's own name counts (einkauf.kessler-feinmechanik@); a lookalike of the customer never counts anywhere.
SENDER_GUARD = os.environ.get("SENDER_GUARD", "on").lower() != "off"
SHARED_DOMAINS = {d.strip().lower() for d in os.environ.get("SHARED_DOMAINS", "hackloop.mail").split(",") if d.strip()}


def imitates_customer(mail: dict, session: dict) -> str | None:
    """The thread's customer address when this reply's sender imitates it (strong or weak lookalike), else None."""
    import lookalike
    sender = parseaddr(mail.get("from") or "")[1].lower()
    customer = parseaddr(session.get("customer") or "")[1].lower()
    if not lookalike.ON or not sender or not customer or sender == customer:
        return None
    return customer if lookalike.strength(sender, customer) else None


def authorised(mail: dict, session: dict) -> bool:
    """The customer's own address (any display name) or a colleague at the same company domain (not a free-mail one)."""
    sender = parseaddr(mail.get("from") or "")[1].lower()
    customer = parseaddr(session.get("customer") or "")[1].lower()
    if not customer or sender == customer:
        return True
    domain = customer.rpartition("@")[2]
    if SENDER_GUARD:
        if imitates_customer(mail, session):
            return False
        if domain in SHARED_DOMAINS and sender.rpartition("@")[2] == domain:
            import lookalike
            own = lookalike._squash(customer.rpartition("@")[0])
            return len(own) >= 6 and own in lookalike._squash(sender.rpartition("@")[0])
    return domain not in FREE_MAIL and sender.rpartition("@")[2] == domain


def authorise_text(session: dict, mail: dict) -> str:
    """Trap 14: one short question to the original contact, no amount, nothing booked."""
    name = (session.get("rfq") or {}).get("contact_name")
    other = parseaddr(mail.get("from") or "")[1]
    if quote_style.QUOTE_STYLE == "between":
        code = str((session.get("rfq") or {}).get("language") or "en").lower()[:2]
        code = code if code in AUTHORISE else "en"
        return short_mail._mail(code, name, AUTHORISE[code].format(other=other),
                                formal=(session.get("rfq") or {}).get("formal"), later=True)
    return (f"{'Hi ' + name.split()[0] + ',' if name else 'Hi,'}\n\nI've just had a go-ahead for this quote from {other}. "
            "Before I book anything, could you confirm it's fine to book? A short yes is all I need.\n\n"
            "Best regards,\nLena\nLeylü Air Freight")


def handle_customer_reply(mail: dict, box, api, session: dict | None) -> None:
    if session is None:  # no session for this thread: nothing to book or hand over, but never crash the worker
        return print(f"reply without a session ignored: #{mail.get('id')} {mail.get('from')}")
    session_id = session["id"]
    api.event(session_id, "mail_in", f"Reply from {mail['from']}: {mail['subject']}", mail_data(mail))
    try:
        if SENDER_GUARD and (real := imitates_customer(mail, session)):
            # a lookalike of this thread's customer (kessler-feinmechanik.mail@ in kessler-feinmechanik@'s thread): no
            # reply at all (Orhun: nothing to lookalikes), no price, no booking; a person checks
            return hand_over(api, session_id, f"Reply from {mail.get('from')}, which imitates the customer address "
                                              f"{real}: nothing sent, nothing booked")
        if session.get("stage") not in ("new", "pricing") and NEW_REQUEST.search(text := latest_text(mail["body"])) \
                and CARGO_FACT.search(text):
            # HACKATHON_GAPS #1: "also, can you quote another shipment: 2 pallets, 300 kg to ORD?" is no yes/no/question
            # about our quote; read as one it would book or be lost. A person quotes it (ntfy alert).
            return hand_over(api, session_id, "New shipment request inside the thread: quote it as a new RFQ")
        # Only while the RFQ agent still prices: a handed-over or paused session goes to a person as before.
        if session.get("stage") in ("new", "pricing") and not session.get("paused") \
                and (not session.get("needs_human") or amendments.held(mail["thread_id"])):  # a correction while we price (or hold the quote): the RFQ agent re-reads it
            amendments.add(mail["thread_id"], mail)
            return api.event(session_id, "routed", "Customer wrote again before our quote: read with the request")
        if session.get("stage") != "quoted":
            text = _plain(latest_text(mail["body"]))
            requested = bool((session.get("booking") or {}).get("pending_email"))  # booked by email, not confirmed yet
            if DECLINE_ACK and _acknowledges_decline(session, text):
                # session 184: "Understood, thanks for letting me know" after our lane decline: nothing to answer
                api.update(session_id, needs_human=False)
                return api.event(session_id, "routed", "Customer acknowledged our decline: no reply needed, closed")
            if (is_booked(session) or requested) and (THANKS.search(text) or THANKS_WORLD.search(text)) \
                    and "?" not in text and "？" not in text and not DECLINE.search(text) \
                    and not CHANGE.search(THANKS_UPDATE.sub(" ", text)) and not THANKS_CHANGE.search(text) \
                    and not CHANGE_WORLD.search(text):
                # "Thank you for booking, let me know once the airline confirms": the confirmation mail answers it
                return api.event(session_id, "routed", "Customer thanked us after the booking (no reply needed)")
            if TRACKING_IN_THREAD and is_booked(session) and is_status_question(text) \
                    and not api.session(session_id).get("paused"):
                reply = tracking_text(session, language.wanted(mail))
                box.reply(mail, reply)
                return api.event(session_id, "tracking_answer", f"Status question in the booking thread answered "
                                                                f"({mail['from']})", reply_data(mail, reply))
            if (is_booked(session) or requested) and CANCEL.search(text) and not NO_CANCEL.search(text) \
                    and CANCEL_AUTO and (session.get("booking") or {}).get("cancel_requested"):
                # R88: "please drop me a note once the airline confirms the cancellation": asked already, no new mail
                return api.event(session_id, "routed", "Cancellation already requested from the airline: no reply needed")
            if (is_booked(session) or requested) and CANCEL.search(text) and not NO_CANCEL.search(text) \
                    and CANCEL_AUTO and (reason := _no_auto_cancel(mail, session, text)):
                return hand_over(api, session_id, reason)  # no mail: never confirm anything to a forged sender
            if (is_booked(session) or requested) and CANCEL.search(text) and not NO_CANCEL.search(text) \
                    and CANCEL_AUTO and not session.get("paused") and _cancel_with_airline(session, mail, box, api):
                return
            if (is_booked(session) or requested) and CANCEL.search(text) and not NO_CANCEL.search(text):
                # Trap 21: never silently left booked: the customer hears we have it, a person cancels with the airline
                reply = cancel_ack_text(session, language.wanted(mail))
                box.reply(mail, reply)
                update = {"at": now(), "text": "Customer asked to cancel the booking: a person handles it with the airline"}
                api.update(session_id, status_updates=[*(session.get("status_updates") or []), update])
                api.event(session_id, "routed", "Cancellation request acknowledged", reply_data(mail, reply))
                return hand_over(api, session_id, "Customer asked to cancel the booking: cancel it with the airline")
            return hand_over(api, session_id, "Customer wrote, but there is no open quote")
        if price_match.ON and not is_booked(session) and (session.get("quote") or {}).get("total") \
                and (price_match.asks(said := _plain(latest_text(mail["body"])))
                     or (other_price(said, session.get("quote")) or 1e12) < float(session["quote"]["total"])) \
                and not (REQUOTE and requote.kind(said, session.get("rfq") or {})) \
                and not api.session(session_id).get("paused") and _price_match(mail, box, api, session, said):
            return  # R111 "another forwarder quoted 7% less, can you match?": our best real all-in, the quote re-pointed
        intent, cost = read_intent(mail["body"], session.get("quote"))
        if cost:
            api.update(session_id, llm_cost_usd=(session.get("llm_cost_usd") or 0) + cost)
        if intent == "decline":
            api.update(session_id, stage="done", outcome="lost")
            return api.event(session_id, "declined", "Customer declined the quote", cost=cost)
        text = _plain(latest_text(mail["body"]))
        rfq = session.get("rfq") or {}
        if intent != "accept" and intent != "wait" and DOCS_BOOK and rfq.get("dangerous_goods") \
                and (mail.get("attachments") or DOCS_SENT.search(text)) and DOCS_PROMISE_WORDS.search(text) \
                and "?" not in text and not CHANGE.search(text) and not CONDITION.search(text) \
                and not counter_offer(text, session.get("quote")) and not api.session(session_id).get("paused"):
            # Trap 4: the papers alone are no yes (they may still want to wait): thank them and ask for the go-ahead
            reply = docs_ack_text({**rfq, "dangerous_goods": False}, session.get("quote") or {})
            box.reply(mail, reply)
            return api.event(session_id, "routed", "DG documents received: thanked, asked for the go-ahead (not booked)",
                             reply_data(mail, reply), cost)
        if CONFIRM_ANSWERS and intent != "accept" and CONFIRM_Q.search(text) and not CONDITION.search(text) \
                and not counter_offer(text, session.get("quote")) \
                and confirms_our_data(text, rfq) and int(rfq.get("auto_answers") or 0) < AUTO_ANSWERS \
                and not NOT_PLAIN_QUOTE.search(THANKS_UPDATE.sub(" ", text)) \
                and (session.get("quote") or {}).get("total") and not api.session(session_id).get("paused"):
            # R60: "Please hold off on booking… Could you please confirm that your offer covers 11 pieces, 1,674 kg…?"
            reply = confirm_text(rfq, session["quote"])
            box.reply(mail, reply)
            api.update(session_id, rfq={**rfq, "auto_answers": int(rfq.get("auto_answers") or 0) + 1})  # same cap
            return api.event(session_id, "routed", "Customer asked us to confirm the quote: confirmed, quote stays open",
                             reply_data(mail, reply), cost)
        if intent == "wait" or (intent != "accept" and "?" not in text and LATER.search(text)
                                and not CHANGE.search(text) and not CONDITION.search(text)):
            return api.event(session_id, "routed", "Customer will decide later: quote stays open, no reply needed",
                             cost=cost)
        change = REQUOTE and not (session.get("booking") or {}).get("booking_reference") and requote.kind(text, rfq)
        if intent == "accept" and REQUOTE and rfq.get("requote_asked") and not change:
            # we asked for their changed figures: a plain yes is a yes to the OLD shipment's rate, never booked
            return hand_over(api, session_id, "A yes after the customer changed the shipment (we asked for the new "
                                              "figures): not booked, the open quote is for the old shipment")
        # also a yes: "yes, book it, it's 1,317 kg now" gets the new quote first, then their next yes books that
        if change \
                and not (session.get("booking") or {}).get("booking_reference") and (session.get("quote") or {}).get("total") \
                and not api.session(session_id).get("paused"):
            # R86 (no answer): "the shipment details have changed to: 5 pieces, 1317 kg … Could you please update your
            # offer?" after our quote. 5U scores the updated offer, so we price the new figures and quote again.
            if MULTI_GUARD and len((session.get("quote") or {}).get("lots") or []) > 1:
                return hand_over(api, session_id, "The customer changed a shipment of a multi-shipment quote: a person "
                                                  "re-quotes (one new price per shipment)")
            import rfq_agent
            return rfq_agent.requote_after_change(mail, box, api, session, ask=change == "ask")
        if intent != "accept":
            if DOCS_ACK and "?" not in text and DOCS_PROMISE.search(text) and not CHANGE.search(text) \
                    and not CONDITION.search(text) and not api.session(session_id).get("paused"):
                reply = docs_ack_text(session.get("rfq") or {}, session.get("quote") or {})
                box.reply(mail, reply)
                return api.event(session_id, "routed", "Customer will send documents: thanked, ready to book on their word",
                                 reply_data(mail, reply), cost)
            if QUOTE_ANSWERS and not CHANGE.search(THANKS_UPDATE.sub(" ", text)) and not CONDITION.search(text) \
                    and not counter_offer(text, session.get("quote")) \
                    and not NOT_PLAIN_QUOTE.search(THANKS_UPDATE.sub(" ", text)) \
                    and (session.get("quote") or {}).get("total") and not api.session(session_id).get("paused"):
                answered = int(rfq.get("auto_answers") or 0)
                topic, topic_cost = (llm.chat_json("topic", TOPIC_PROMPT, text, TOPIC_SCHEMA) if answered < AUTO_ANSWERS
                                     else ({"topic": "other"}, 0.0))
                if topic.get("topic", "other") != "other":
                    reply = quote_style.quote_summary_text(rfq, session["quote"], mail["body"])
                    box.reply(mail, reply)
                    api.update(session_id, rfq={**rfq, "auto_answers": answered + 1})
                    return api.event(session_id, "routed", f"Customer asked about the quote ({topic.get('topic')}): answered",
                                     reply_data(mail, reply), cost + topic_cost)
            return hand_over(api, session_id, "Customer replied with a question")
        if not authorised(mail, session):
            # Trap 14: a yes from someone outside the customer's company never books: the original contact confirms
            contact = {**mail, "from": session["customer"]}
            reply = authorise_text(session, mail)
            box.reply(contact, reply)
            return api.event(session_id, "routed", f"Yes from {mail['from']}, not the customer's address or company: "
                             "not booked, asked the original contact to confirm", reply_data(contact, reply), cost)
        with _session_lock(session_id):
            current = api.session(session_id)  # another reply may have booked it in the meantime
            if is_booked(current) or current.get("stage") != "quoted":
                return api.event(session_id, "accepted", "Already booked: second acceptance ignored", cost=cost)
            if _before_our_new_price(mail, current.get("quote") or {}):
                return api.event(session_id, "routed", "A yes to the old price, written before our new-price mail: "
                                 "not booked, waiting for their answer to the new price", cost=cost)
            api.event(session_id, "accepted", "Customer accepted the quote", cost=cost)
            bid = accepted_bid(current)
            if bid and bid.get("withdrawn"):
                return _withdrawn_ask_again(mail, box, api, current, cost)
            if bid and bid.get("conditional"):  # trap 15: the carrier reconfirms before the customer hears "booked"
                if not book_by_email(current, box, api, f"conditional offer: {bid['conditional']}"):
                    return hand_over(api, session_id, f"Accepted a conditional offer ({bid['conditional']}) and the "
                                                      "carrier has no booking address: a person reconfirms and books")
                text = booking_requested_text(current)
                box.reply(mail, text)
                return api.event(session_id, "routed", "Conditional offer: carrier asked to reconfirm, customer told "
                                 "the booking is requested", reply_data(mail, text))
            try:
                booking = api.book(session_id, current["quote"].get("rate_id"))
            except Exception as error:  # the portal can't book this option at all: book by email instead
                if change := price_changed(error):  # never book another price than the one accepted (R48, R49)
                    return ask_again_at_new_price(mail, box, api, api.session(session_id), change)
                if not portal_cannot_book(error):
                    raise  # timeout, 502, portal down: it may have booked, so a person checks (as before)
                latest = api.session(session_id)
                if is_booked(latest):  # booked after all: carry on with that booking
                    booking = latest["booking"]
                elif book_by_email(latest, box, api, getattr(getattr(error, "response", None), "text", "")[:200]):
                    text = booking_requested_text(latest)
                    box.reply(mail, text)
                    return api.event(session_id, "routed", "Customer told the booking is requested",
                                     reply_data(mail, text))
                else:
                    raise
            # Store it before anything else: bookings are real and public, a pause must not lose one.
            api.update(session_id, stage="booked", outcome="won", booking={**booking, "booked_at": now()})
        if api.session(session_id).get("paused"):
            return api.event(session_id, "booked", f"Booked {booking['booking_reference']}; mail held: paused", booking)
        text = booking_text(session["rfq"], booking)
        box.reply(mail, text)
        api.event(session_id, "booked", f"Booked with {booking['airline']}: {booking['booking_reference']}",
                  {**booking, **reply_data(mail, text)})
    except Exception as error:  # the session shows what happened; the worker keeps going
        api.update(session_id, needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")


# Trap 12: a "Booking BK-… confirmed" mail counts only from the airline we booked with (its kit-list address, or the
# address we asked by email) and only while that booking waits for it; anything else is ignored with a session note.
CONFIRM_SENDER = os.environ.get("CONFIRM_SENDER", "on").lower() != "off"


def _from_our_airline(sender: str, session: dict) -> bool:
    booking, quote = session.get("booking") or {}, session.get("quote") or {}
    expected = {booking.get("pending_email"), airline_email(booking.get("airline")), airline_email(quote.get("carrier"))}
    expected.discard(None)
    if expected:
        return sender in expected
    return sender in {c["email"].lower() for c in load_carriers() if c.get("kind") == "airline"}  # airline not listed


def handle_booking_confirmed(mail: dict, box, api) -> bool:
    """The airline confirmed a booking: record it and tell the customer. False if the mail isn't one."""
    match = CONFIRMED.search(f"{mail['subject']}\n{mail['body']}")
    if not match:
        return False
    reference = match.group(1).upper()
    sender = parseaddr(mail.get("from") or "")[1].lower()
    session = api.find(reference=reference)
    by_email = session is None and (session := _email_booking_of(mail, api)) is not None
    if session is None:
        print(f"confirmation for unknown booking {reference}")
        return True
    if CANCEL_AUTO and (session.get("booking") or {}).get("cancel_requested"):
        if cancellation_confirmed(session, mail, box, api):
            return True
        api.event(session["id"], "routed", f"Airline confirmed {reference} after our cancellation request: not passed "
                                           "on, waiting for their cancellation", mail_data(mail))
        b = session.get("booking") or {}
        api.update(session["id"], booking={**b, "booking_reference": b.get("booking_reference") or reference})
        return True
    if CONFIRM_SENDER and not by_email and (not _from_our_airline(sender, session)
                                            or (session.get("booking") or {}).get("status") == "confirmed"):
        api.event(session["id"], "routed", f"Confirmation of {reference} from {sender} ignored: not from the booked "
                                           "airline, or the booking is already confirmed", mail_data(mail))
        return True
    update = {"at": now(), "text": f"Booking {reference} confirmed by the airline"}
    booking = {**(session.get("booking") or {}), "booking_reference": reference, "status": "confirmed"}
    session = {**session, "booking": booking}  # R46: the confirmation text needs the reference (KeyError before)
    api.update(session["id"], booking=booking,
               **({"needs_human": False} if by_email else {}),
               status_updates=[*(session.get("status_updates") or []), update])
    data = {}
    if not session.get("paused"):
        thread = {"id": session["thread_id"], "thread_id": session["thread_id"], "from": session["customer"],
                  "subject": "Your air freight booking"}
        text = booking_confirmed_text(session)
        box.reply(thread, text)
        data = reply_data(thread, text)
    api.event(session["id"], "status_sent", update["text"], data)
    return True


# What the airline says happened, as fixed English phrases (never their own text: it goes to the customer).
UPDATE_EVENTS = (
    ("offloaded", re.compile(r"\boff-?load\w*|\brolled\b|\bbumped\b|nicht\s+verladen|ausgeladen", re.I),
     "it was offloaded from the planned flight"),
    ("rebooked", re.compile(r"\bre-?book\w*|next\s+(?:available\s+)?flight|umgebucht|n[äa]chste\w*\s+flug", re.I),
     "it is rebooked on the next available flight"),
    ("cancelled", re.compile(r"\bcancel+\w*|\bstorn\w*|annul\w*", re.I), "the planned flight was cancelled"),
    ("delayed", re.compile(r"\bdelay\w*|versp[äa]t\w*|\blater\s+departure", re.I), "the flight is delayed"),
    ("departed", re.compile(r"\bdeparted\b|\bairborne\b|\bwheels\s+up\b|abgeflogen", re.I), "it has departed"),
    ("arrived", re.compile(r"\barrived\b|\blanded\b|angekommen|gelandet", re.I), "it has arrived at destination"),
)
TELL_CUSTOMER = {"offloaded", "rebooked", "cancelled", "delayed"}  # news that changes their plans
_MONTH = r"(?:jan|feb|mar|mär|apr|may|mai|jun|jul|aug|sep|oct|okt|nov|dec|dez)[a-zä]*"
# no currency between the word and the date ("charges expected: EUR 12.50" is no ETA: the note never names an amount)
NEW_ETA = re.compile(r"\b(?:new\s+)?(?:eta|arrival|ankunft|expected|voraussichtlich\w*)\b"
                     r"(?:(?!(?:EUR|USD|GBP|CHF)\b)[^\n\d€$£]){0,30}?"
                     r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./](?:1[0-2]|0?[1-9])(?!\d)\.?(?:\d{2,4})?|\d{1,2}\.?\s+" + _MONTH + r"(?:\s+\d{4})?|"
                     + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)", re.I)


def airline_update(text: str) -> tuple[list[str], str | None]:
    """(events, new ETA as written) the airline's mail reports, rules only."""
    events = [key for key, pattern, _ in UPDATE_EVENTS if pattern.search(text or "")]
    eta = NEW_ETA.search(text or "")
    return events, (eta.group(1).strip() if eta else None)


def booking_update_text(session: dict, events: list[str], eta: str | None) -> str:
    booking, rfq = session.get("booking") or {}, session.get("rfq") or {}
    first = ((rfq.get("contact_name") or "").split() or [None])[0]
    news = "; ".join(text for key, _, text in UPDATE_EVENTS if key in events)
    if eta and short_mail.ISO_DAY.fullmatch(eta.strip()):
        eta = short_mail.day("en", eta.strip())  # "30 Nov", never 2026-11-30
    when = f" The new expected arrival is {eta}." if eta else ""
    return (f"{'Hi ' + first + ',' if first else 'Hi,'}\n\na quick update on booking {booking.get('booking_reference')} "
            f"({rfq.get('origin')} to {rfq.get('destination')}): {booking.get('airline') or 'the airline'} let us know "
            f"that {news}.{when} I'm on it and will keep you posted.\n\n" + short_mail._sign("en"))


def handle_booking_update(mail: dict, box, api) -> bool:
    """AIRLINE_UPDATES: an airline mail about our booking (offload, rebooking, delay, new ETA): record it in the CRM
    (tracking answers with it) and tell the customer when it changes their plans. False if it names no booking of ours."""
    from router import BOOKING_REF
    text = f"{mail.get('subject') or ''}\n{latest_text(mail.get('body') or '')}"
    match = BOOKING_REF.search(text)
    session = api.find(reference=match.group(1).upper()) if match else None
    if session is None:
        print(f"airline update for an unknown booking: {mail.get('subject')}")
        return False
    if cancellation_confirmed(session, mail, box, api):
        return True
    events, eta = airline_update(text)
    reference = match.group(1).upper()
    sender = parseaddr(mail.get("from") or "")[1].lower()
    if CONFIRM_SENDER and not _from_our_airline(sender, session):  # trap 12: only the booked airline updates it
        api.event(session["id"], "routed", f"Airline update on {reference} from {sender} ignored: not the booked airline",
                  mail_data(mail))
        return True
    summary = "; ".join(t for k, _, t in UPDATE_EVENTS if k in events) or "an update from the airline"
    update = {"at": now(), "text": f"Booking {reference}: {summary}" + (f", new expected arrival {eta}" if eta else "")}
    api.update(session["id"], status_updates=[*(session.get("status_updates") or []), update])
    data = {}
    if TELL_CUSTOMER & set(events) and not session.get("paused"):
        thread = {"id": session["thread_id"], "thread_id": session["thread_id"], "from": session["customer"],
                  "subject": "Your air freight booking"}
        body = booking_update_text(session, events, eta)
        box.reply(thread, body)
        data = reply_data(thread, body)
    api.event(session["id"], "status_sent" if data else "status", update["text"], data)
    return True


def _email_booking_of(mail: dict, api) -> dict | None:
    """The session that asked this airline (exact sender) to book by email and has no booking reference yet. Trap 13:
    with several waiting, only our reference (S-<id>) in the mail or the thread of our request picks one; else a
    person matches it (never the newest by guess)."""
    sender = parseaddr(mail.get("from") or "")[1].lower()  # "Meridian Freightways <meridian-…@…>" too
    try:
        waiting = [s for s in api.sessions() if (s.get("booking") or {}).get("pending_email") == sender
                   and not (s.get("booking") or {}).get("booking_reference")]
    except Exception:  # a lookup hiccup must not lose the airline's mail: it is still logged as unknown
        return None
    if len(waiting) <= 1:
        return waiting[0] if waiting else None
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    named = [s for s in waiting if re.search(rf"\bS-{s['id']}\b", text, re.I)
             or (s.get("booking") or {}).get("request_thread_id") == mail.get("thread_id")]
    if len(named) == 1:
        return named[0]
    for s in waiting:
        hand_over(api, s["id"], f"Airline confirmation {CONFIRMED.search(text)[1].upper()} from {sender} fits {len(waiting)} pending email bookings: "
                                "match it by hand")
    return None
