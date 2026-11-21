"""REGISTER: answer in the customer's register. Rules only, no LLM.

German: a formal RFQ ("Sehr geehrte", "Guten Tag", "Sie", "Ihnen", "Mit freundlichen Grüßen") gets "Guten Tag Frau Berg,"
(only when the mail itself writes Herr/Frau: a gender is never guessed from a first name), else "Guten Tag Anna Berg,",
and a formal closing; an informal one ("du", "dein", "euch") gets "Hallo Anna," and du / ihr all through. French "tu" and
Spanish "tú" get the informal forms too (vous / usted stay the default). Nothing clear: the old wording (Hallo + Sie).
REGISTER=off (default since #212: our voice never copies the sender's style; on = mirror Sie / du).
"""

import os
import re

REGISTER = os.environ.get("REGISTER", "off").lower() == "on"

DE_DU = re.compile(r"\b(?:du|dich|dir|dein|deine[nmrs]?|hast\s+du|kannst\s+du|schick\s+mir)\b", re.I)
DE_IHR = re.compile(r"\b(?:euch|euer|eure[nmrs]?|habt\s+ihr|könnt\s+ihr)\b", re.I)
DE_SIE = re.compile(r"(?<![.!?]\s)\b(?:Sie|Ihnen|Ihre[nmrs]?|Ihr)\b|\b(?:sehr\s+geehrte\w*|guten\s+tag|"
                    r"mit\s+freundlichen\s+gr(?:ü|ue)(?:ß|ss)en|hochachtungsvoll)\b", re.M)
DE_SIE_WORDS = re.compile(r"\b(?:sehr\s+geehrte\w*|guten\s+tag|mit\s+freundlichen\s+gr(?:ü|ue)(?:ß|ss)en|"
                          r"hochachtungsvoll|können\s+sie|würden\s+sie|bitten\s+sie|senden\s+sie|ihnen)\b", re.I)
FR_TU = re.compile(r"\b(?:tu|toi|ton|ta|tes|t['’]|salut|peux-tu|pourrais-tu|envoie-moi|dis-moi)\b", re.I)
FR_VOUS = re.compile(r"\b(?:vous|votre|vos|madame|monsieur|cordialement)\b", re.I)
ES_TU = re.compile(r"\b(?:tú|tus|puedes|podrías|mándame|envíame|dime|te\s+(?:pido|escribo|agradezco))\b", re.I)
ES_USTED = re.compile(r"\b(?:usted|ustedes|su\s+oferta|estimad[oa]s?|le\s+(?:pido|agradezco|escribo)|"
                      r"atentamente|cordialmente)\b", re.I)
SALUTATION = re.compile(r"\b(Herr|Frau)\s+(?:Dr\.\s*|Prof\.\s*)?(?:[A-ZÄÖÜ][a-zäöüß]+\s+)?([A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ]"
                        r"[a-zäöüß]+)?)\b")


def read(text: str, language: str | None) -> str | None:
    """'formal', 'informal' or None from the customer's own words in that language."""
    if not REGISTER:
        return None
    lang = (language or "")[:2].lower()
    text = text or ""
    if lang == "de":
        if DE_SIE_WORDS.search(text):
            return "formal"
        if DE_DU.search(text) or DE_IHR.search(text):
            return "informal"
        return "formal" if DE_SIE.search(text) else None
    if lang == "fr":
        return "informal" if FR_TU.search(text) and not FR_VOUS.search(text) else ("formal" if FR_VOUS.search(text)
                                                                                    else None)
    if lang == "es":
        return "informal" if ES_TU.search(text) and not ES_USTED.search(text) else ("formal" if ES_USTED.search(text)
                                                                                     else None)
    return None


def plural(text: str) -> bool:
    """German informal plural: "könnt ihr", "euch", "eure"."""
    return bool(DE_IHR.search(text or ""))


def salutation(text: str) -> str | None:
    """'Frau Berg' / 'Herr Huber' when the mail names the sender that way (signature, "i.A. Frau Berg")."""
    found = SALUTATION.findall(text or "")
    return f"{found[-1][0]} {found[-1][1]}" if found else None
