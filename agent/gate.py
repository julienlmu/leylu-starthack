"""Quote gate: the last check before a quote leaves. Free (rules only, no LLM), runs on every quote.

Every rejected round so far was a quote a careful forwarder would have stopped: round 1 `too_low` (door-to-port
without the trucking), rounds 10 and 11 `dg_docs_missing` (dangerous goods named only in the attachment). Each new
trap so far has been "something in the request the quote must react to". The gate collects those reactions in one
place, so a new trap is one more rule here, not a patch spread over extract, pricing and templates.

review() returns findings, each with a level:
- fix:  we change the quote ourselves (pick another option, add a sentence the customer needs). Sent as usual.
- hold: a person should look. The session is flagged (ntfy push via the backend) and the quote still goes out on its
        own at GATE_AUTO_SEND_SECONDS after the RFQ, because no answer scores nothing (dead man's switch).
- note: only logged.

Added sentences never contain digits: a quote states exactly one amount (the scorer reads it).
GATE_MODE=enforce (default) | warn (log only, change nothing, never hold) | off: switch without a deploy.
"""

import os
import re
import statistics
from datetime import date, timedelta

import constraints
import shapes

MODE = os.environ.get("GATE_MODE", "enforce").lower()
OUTLIER_RATIO = float(os.environ.get("GATE_OUTLIER_RATIO", "0.5"))  # chosen below half the median → a part is missing
MONEY = re.compile(r"\d[\d,.]*\.\d{2}")

# ---- special cargo: what the request says → what the quote must say ------------------------------------------------
# DG beyond the words dg.py / attachments.py already catch. A hit sets rfq["dangerous_goods"], so the template's
# own DG paragraph (MSDS + DGD, 8 languages) is used: never two DG paragraphs.
DG_EXTRA = re.compile(
    r"\b(UN\s?-?\d{4}|dry\s*ice|carbon\s+dioxide,?\s+solid|radioactive|infectious\s+substances?|biological\s+substances?"
    r"|corrosive|oxidi[sz]ing|toxic\s+substances?|compressed\s+gas|gas\s+cylinders?|fireworks|safety\s+matches|"
    r"magneti[sz]ed\s+material|flash\s*point|IATA\s+DGR|hazard\s+class|packing\s+group\s+(?:I{1,3}|[123])|"
    r"Gefahrgut(?:klasse)?|matières\s+dangereuses|mercancías?\s+peligrosas?|tehlikeli\s+madde)\b", re.I)
NEGATED = re.compile(r"\b(?:non|not|no|kein\w*|nicht)[- ]?(?:dangerous|hazardous|corrosive|toxic|radioactive|"
                     r"flammable|magneti[sz]ed|Gefahrgut)\b", re.I)

# code, pattern, level, English sentence, German sentence (other languages get the English one)
SPECIAL = [
    ("temperature", re.compile(r"temperature[- ]?(?:controlled|sensitive)|cold[- ]chain|refrigerated|reefer|"
                               r"deep[- ]?frozen|\bfrozen\b|\bchilled\b|keep\s+(?:cool|cold|refrigerated)|"
                               r"\d\s*(?:-|–|to|and|bis)\s*\+?\d+\s*°\s?C\b|gekühlt|Kühlkette|Kühlware|tiefgekühlt",
                               re.I), "fix",
     "As the goods need a controlled temperature, we book them as temperature-controlled cargo: please confirm the "
     "required range and whether a data logger travels with the shipment.",
     "Da die Ware temperaturgeführt reisen muss, buchen wir sie als temperaturkontrollierte Fracht: bitte bestätigen "
     "Sie uns den nötigen Temperaturbereich und ob ein Datenlogger mitreist."),
    ("perishable", re.compile(r"perishables?|fresh\s+(?:flowers|fish|meat|fruit|produce)|seafood|cut\s+flowers|"
                              r"verderbliche?", re.I), "fix",
     "We book the shipment as perishable cargo with priority handling at both airports.",
     "Wir buchen die Sendung als verderbliche Ware mit bevorzugter Abfertigung an beiden Flughäfen."),
    ("valuables", re.compile(r"\b(?:gold\s+bars|bullion|jewell?e?ry|banknotes|precious\s+(?:metals|stones)|"
                             r"diamonds|valuables|Wertfracht|Schmuck)\b", re.I), "fix",
     "As valuable cargo the shipment gets secure handling and storage; please let us know the declared value.",
     "Als Wertfracht wird die Sendung gesichert abgefertigt und gelagert; bitte nennen Sie uns den deklarierten Wert."),
    ("non_stackable", re.compile(r"non[- ]?stackable|not\s+stackable|do\s+not\s+stack|nicht\s+stapelbar", re.I), "fix",
     "We have noted that the pieces must not be stacked and book the space accordingly.",
     "Wir haben vermerkt, dass die Packstücke nicht gestapelt werden dürfen, und buchen den Platz entsprechend."),
    ("live_animals", re.compile(r"\blive\s+(?:animals?|fish|birds|insects)|livestock|hatching\s+eggs|"
                                r"lebende\s+Tiere", re.I), "hold",
     "", ""),
    ("human_remains", re.compile(r"human\s+remains|\bcoffin\b|Leichnam", re.I), "hold", "", ""),
    ("sea_freight", re.compile(r"\b(?:sea|ocean)\s+freight|by\s+sea|\bFCL\b|\bLCL\b|Seefracht", re.I), "note", "", ""),
]
# ---- CARGO_WORDS_V2 (cargo-price sweep): more phrasings in EN/DE/FR/IT/ES, each hit read with its own negation ----
# Off (CARGO_WORDS_V2=off) = DG_EXTRA / NEGATED / SPECIAL above, exactly as before.
# A hit is negated when a "no / not / kein / ohne / pas / sin / senza ..." stands up to five words before it in the same
# clause ("no dangerous goods", "nicht um Gefahrgut", "pas de matières dangereuses"), when the next words answer no
# ("Gefahrgut: nein", "Dangerous goods: N/A", "fragrance-free", "lithium batteries are not included"), or when it
# continues a negated list ("no aerosols, perfumes or lithium batteries"). A comma ends the clause, so "Not stackable,
# dry ice inside" is dry ice. Misses cost a reject (dg_docs_missing), so unclear cases count as DG.
CARGO_WORDS_V2 = os.environ.get("CARGO_WORDS_V2", "on").lower() != "off"
_TERMS = lambda *alts: re.compile("|".join(alts), re.I)  # noqa: E731
DG_V2 = _TERMS(
    # UN numbers ("UN 3480", "UN-3481", "UN3091", "UN No. 1263", "UN-Nr. 1993", "UN#1845", "ONU 1263"); a lowercase
    # "un" only glued to the digits ("un3480"), never the French/Spanish article. Exactly four digits, not a reference
    # number ("Our ref UN-2024-118", "PO UN 4711": _not_the_goods)
    r"(?-i:\b(?:UN|ONU))\s?(?:-\s?)?(?:#\s?|(?:No|NO|Nr|Nummer|[Nn]umber|n[°º])\.?\s?:?\s?)?\d{4}\b(?![-/.]\d)",
    r"(?-i:\bun-?\d{4}\b(?![-/.]\d))",
    # typos: a letter O for a zero ("UN 348O"), "U.N. 3480", the number split once ("UN 3 480")
    r"(?-i:\bUN)\s?-?\s?(?:\d{3}[Oo]|\d{2}[Oo]\d|\d[Oo]\d{2}|[Oo]\d{3})\b", r"(?-i:\bU\.N\.)\s?-?\s?\d{4}\b(?![-/.]\d)",
    r"(?-i:\bUN)\s?\d\s\d{3}\b(?![-/.]\d)",
    r"\bUN\s?38\.3\b",
    # classes, packing groups, regulations (a bare "Class 9" is read in code: _class_hit)
    r"(?-i:\b(?:DG|IMO|IMDG|IATA|ADR))[\s:-]*(?:class|klasse|klase|classe|clase)\s*:?\s*[1-9]\b",
    r"\b(?:hazard(?:ous)?|haz(?:mat)?|dangerous\s+goods|danger|Gefahr(?:gut)?)[\s:-]*(?:class|klasse|klase|classe|clase)\s*:?\s*[1-9]\b",
    r"\b(?:class|klasse|classe|clase|division)\s*:?\s*(?:1\.[1-6]|2\.[1-3]|4\.[1-3]|5\.[12]|6\.[12])\b",
    r"(?-i:\bPG\s?I{1,3}\b)", r"\bpacking\s+group\s+(?:I{1,3}|[123])\b", r"\bVerpackungsgruppe\s+(?:I{1,3}|[123])\b",
    r"(?-i:\b(?:IMDG|IATA[- ]DGR|DGR|ADR)\b)", r"\bhaz[- ]?mat\b", r"\bexcepted\s+quantit(?:y|ies)\b",
    r"\b(?:packed|shipped|declared)\s+(?:in|as)\s+limited\s+quantit(?:y|ies)\b", r"\blimited\s+quantit(?:y|ies)\s*\(LQ\)",
    r"\bdang(?:erous|erouse|erus|eros|rous)\s+(?:goods?|cargo|materials?|substances?)\b",
    r"\bhaz(?:ardous|ardus|ardious|ardos|zardous)\s+(?:materials?|goods|cargo|substances?|chemicals?|waste)\b",
    r"(?-i:\b(?:dg|Dg))[- ](?:cargo|goods|shipment)\b", r"\bhaz[- ](?:cargo|goods)\b",
    r"(?-i:\bDGD\b)", r"(?-i:\bDG)[- ](?:cargo|goods|shipment|declaration|docs?|documents?|items?|surcharge|class)\b",
    r"(?-i:\bDG)\s*[:=?]\s*\|?\s*(?:yes|ja|oui|s[ií]|y)\b", r"\bhazardous\s*[:=?]\s*\|?\s*(?:yes|ja|oui|s[ií]|y)\b",
    r"\bShipper'?s\s+Declaration\s+for\s+Dangerous\b",
    r"\bGefahrg[uü]t(?!\w*frei)\w*", r"\bGef(?:ah|aeh|äh)r(?:en)?g(?:ue|u|ü)t(?!\w*frei)\w*", r"\bgef[äa]hrliche[nr]?\s+G[üu]ter\b",
    r"\b(?:mati[èe]res?|marchandises?)\s+dangereuses?\b", r"\b(?:mercanc[ií]as?|materiales?)\s+peligros[oa]s?\b",
    r"\b(?:merci|merce|materiali?)\s+pericolos[aeio]\b", r"\btehlikeli\s+(?:madde|y[üu]k)\w*",
    r"\bgevaarlijke\s+(?:stoffen|goederen)\b", r"\b(?:towary|materia[łl]y)\s+niebezpieczne\b",
    r"\bmercadorias?\s+perigosas?\b",
    # lithium in every spelling, PI 965-970, battery-powered goods
    r"\bli(?:thi?u[mn]|thuim|thim|tium)(?:[- ]?ionen?|[- ]?polymer|[- ]?metall?)?(?:[- ]?(?:batter\w*|akku\w*|zellen?|cells?))?\b"
    r"(?![- ]?(?:free|frei|grease|soap|stearate|carbonate|disilicate))",
    r"\bLithium\w*(?:batterie|akku|zelle)\w*", r"\bli[- ]?(?:ion(?:en)?|po|polymer)\b(?:[- ]?(?:akku|batter)\w*)?",
    r"\b(?:piles?|batteries?|batterie|bater[ií]as?|pilas?)\s+(?:au|al|de|di|agli\s+ioni\s+di|de\s+iones\s+de|aux\s+ions)\s+lit(?:hium|io)\b",
    r"\blityum\b", r"(?-i:\bPI)\s?9(?:6[5-9]|70)\b",
    r"\b(?:packing\s+instruction|Verpackungsanweisung|instruction\s+d'emballage)\s*:?\s*\d{3}\b",
    r"\bpower\s?banks?\b", r"\b(?:e-?cigarettes?|e-?zigaretten?|vapes?|vaping\s+devices?)\b",
    r"\b(?:e-?bikes?|pedelecs?|e-?scooters?|hoverboards?|electric\s+(?:bikes?|bicycles?|scooters?))\b"
    r"(?!\s*(?:helmets?|frames?|spare|parts|accessor\w*|tyres|tires|saddles?|locks?|racks?|bags?|covers?|chargers?))",
    # dry ice, aerosols, perfumes, paints, flammable liquids
    r"\bdry[\s-]*ice\b", r"\bTrockeneis\b", r"\bglace\s+carbonique\b", r"\bcarboglace\b", r"\bhielo\s+seco\b",
    r"\bghiaccio\s+secco\b", r"\bdroogijs\b", r"\bkuru\s+buz\b", r"\bsuchy\s+l[óo]d\b", r"\bsolid\s+CO2\b",
    r"\bCO2\s+ice\b", r"\bcarbon\s+dioxide,?\s+solid\b",
    r"\baerosol\w*", r"\baersol\w*", r"\ba[ée]rosols?\b", r"\bspray\s*cans?\b", r"\bspray\s+paints?\b", r"\bSpr(?:ay|üh)dosen?\b",
    r"\bDruckgas(?:packung|dose)\w*",
    r"\bperfum(?:es?|s)?\b", r"\bparf[uü]m(?!\w*frei)\w*", r"\bfragrances?\b(?![- ]free)",
    r"\beau\s+de\s+(?:parfum|toilette|cologne)\b", r"\bprofum[io]\b", r"\bDuftstoffe?\b",
    r"\b(?:paints?|varnish(?:es)?|lacquers?|thinners|paint\s+thinner|nail\s+(?:polish|varnish)|Nagellack\w*|(?-i:Lacke?)|Lackfarben?|"
    r"Verd[üu]nn(?:er|ung)|peintures?|vernis|pinturas?|barnices?|vernic[ei]|printing\s+inks?|Druckfarben?|wood\s+stains?)\b"
    r"(?!\s*(?:brush\w*|rollers?|booths?|guns?|sprayers?|spray\s+guns?|equipment|machines?|mixers?|shakers?|lines?|"
    r"jobs?|trays?|pens?|markers?|protection))",
    r"\bsolvents?\b", r"\badhesiv(?:es?)?\b", r"\bglues?\b",
    r"\b(?:in)?flamm?ab(?:le|el)s?\b", r"\binfiammabil[ei]\b", r"\bentz[üu]nd(?:bar|lich)\w*",
    r"\bleichtentz[üu]ndlich\w*", r"(?<!schwer )(?<!schwer)\bentflammbar\w*", r"\bbrennbare\s+Fl[üu]ssigkeit\w*",
    r"\bflash\s*point\b", r"\bFlammpunkt\b",
    r"\b(?:ethanol|isopropanol|isopropyl\s+alcohol|methanol|acetone|Aceton|Brennspiritus|hand\s+sanitizers?)\b",
    # other classes
    r"\b[ck]or+os+i(?:ves?|fs?|vos?|v[io]|v)\b", r"\b[äa]tzend\w*", r"\boxidi[sz](?:ing|ers?)\b", r"\bbrandf[öo]rdernd\w*",
    r"\btoxic\s+substances?\b", r"\bgiftig\w*", r"\bradioa(?:ctive|ktiv\w*)\b", r"\bisotopes?\b",
    r"\binfectious\s+substances?\b", r"\bbiological\s+substances?\b",
    r"\bexplosiv(?:es?|\w*)\b", r"\bammunition\b", r"\bMunition\b", r"\bSprengstoff\w*", r"\bdetonators?\b",
    r"\bfireworks?\b", r"\bFeuerwerk\w*", r"\bpyrotechni\w*", r"\bsafety\s+matches\b",
    # Batu's probe (Sat 22:45): still missed everywhere
    r"\b(?:strike[- ]anywhere|wooden|wax|book)\s+matches\b", r"\bmatches\s*\((?:safety|strike)", r"\bStreichh[öo]lz\w*",
    r"\b(?:power[- ]device|tool|nail[- ]gun|fixing[- ]tool|stud[- ]driver)\s+cartridges?\b",
    r"\bcartridges?\s+for\s+(?:(?:power|nail|fixing|stud)[- ]?)?(?:tools?|guns?|drivers?)\b", r"\bKartuschen?\s+f[üu]r\s+\w*ger[äa]te\b",
    r"\bfuel\s+cells?\b(?:\s+(?:cartridges?|systems?|engines?|modules?|stacks?))?", r"\bBrennstoffzell\w*",
    r"\bsmoke\s+(?:detectors?|alarms?)\b", r"\bRauchmelder\w*", r"\bAm-?\s?241\b", r"\bamericium\b",
    r"危险[品货]", r"危险货物", r"锂电池", r"锂离子", r"第\s?[1-9]\s?类",
    r"\b(?:cigarette|gas|butane|pocket)\s+lighters?\b", r"\bFeuerzeuge?\b",
    r"\bairbags?(?:\s+modules?)?\b", r"\b(?:seat\s*belt\s+)?pretensioners?\b", r"\bGurtstraffer\w*",
    r"\bfire\s+extinguishers?\b", r"\bFeuerl[öo]scher\w*", r"\bcompressed\s+gas\w*", r"\bgas\s+cylinders?\b",
    r"\b(?:Druck)?[Gg]asflaschen?\b", r"\bGaskartuschen?\b", r"\bcamping\s+gas\b",
    r"\b(?:oxygen|helium|nitrogen|argon|propane|butane|acetylene|CO2|hydrogen)\s+(?:cylinders?|bottles?|tanks?|cartridges?|canisters?)\b",
    r"\b(?:car|lead[- ]acid|wet|wet[- ]cell|vehicle|starter)\s+batter(?:y|ies)\b", r"\b(?:Auto|Starter|Blei)(?:batterie|akku)\w*",
    r"\b(?:sulfuric|sulphuric|hydrochloric|nitric|phosphoric|hydrofluoric)\s+acid\b", r"\bbattery\s+acid\b",
    r"\b(?:Schwefel|Salz|Salpeter|Fluss)s[äa]ure\b", r"\bhydrogen\s+peroxide\b", r"\bWasserstoffperoxid\b",
    r"\b(?:pesticides?|insecticides?|herbicides?|fungicides?|Pestizide?|Insektizide?|Herbizide?)\b",
    r"\bneodymium\b", r"\bNeodym\w*", r"\bmagneti[sz]ed\s+(?:material|goods|items)\b", r"\bmagnetic\s+material\b",
    r"\bstrong\s+magnets?\b", r"\bmercury\s+(?:thermometers?|switches?|lamps?)\b", r"\bQuecksilber\w*",
    # Batu's real-life probe (Sat 23:20): 134 of 165 goods an airline treats as DG were missed. A hit only adds the DG
    # papers line to the quote (no price change), so a cautious hit is cheap and a miss costs the round (dg_docs_missing).
    r"\blighters\b", r"\b(?:butane|propane|LPG|camping|gas)\s+(?:gas\s+)?(?:cartridges?|canisters?|refills?)\b",
    r"\b(?:butane|propane|Propan|Butan|acetylene|Acetylen|LPG|Fl[üu]ssiggas)\b(?!\s*(?:-?free|frei))",
    r"\bcompressed\s+(?:air|nitrogen|oxygen|argon|helium)\b", r"\bliquid\s+(?:nitrogen|oxygen|helium)\b",
    r"\bFl[üu]ssigstickstoff\b", r"\brefrigerant(?:\s+gas(?:es)?)?\b", r"\bR-?(?:134a|404A|407C|410A|1234yf|600a|290)\b",
    r"\bK[äa]ltemittel\w*", r"\bnitrous\s+oxide\b", r"\bLachgas\b", r"\b(?:whipped\s+)?cream\s+chargers?\b",
    r"\bSahnekapseln\b", r"\b(?:soda|CO2|seltzer)\s+(?:siphon\s+)?(?:cartridges?|capsules?|cylinders?|chargers?)\b",
    r"\bcalibration\s+gas(?:es)?\b", r"\bPr[üu]fgas\w*", r"\bmedical\s+oxygen\b", r"\bhydrogen\s+gas\b",
    r"\bcamping\s+stoves?\b", r"\bCampingkocher\b",
    r"\b(?:gasoline|petrol|kerosene|Kerosin|jet\s+fuel|diesel\s+fuel|Dieselkraftstoff|lamp\s+oil|Lampen[öo]l|"
    r"lighter\s+fluid|white\s+spirits?|Testbenzin|turpentine|Terpentin\w*|xylene|Xylol|toluene|Toluol|benzene|Benzol|"
    r"methyl\s+ethyl\s+ketone|ethyl\s+acetate|Ethylacetat|formaldehyde?|Formaldehyd|formalin|nitrocellulose|"
    r"Nitrocellulose|celluloid)\b",
    r"(?<![Ff]uel-)(?<![Ff]uel\s)\bBenzin\b(?!\s*-?(?:pumpe|filter|schlauch|leitung|kanister\s+leer))",
    r"\b(?:alcohol|Alkohol)[- ]?(?:gel|based|haltig\w*)\b|\bhand\s+(?:sanitizer|sanitiser|disinfectant)s?\b",
    r"\b(?:disinfectants?|Desinfektionsmittel\w*|isopropyl|IPA\s+cleaner)\b",
    r"\b(?:essential|aromatic)\s+oils?\b", r"\b[äa]therische\s+[ÖöOo]le?\b",
    r"\b(?:after[- ]?shave|hair\s?spray|Haarspray|deodorant\s+sprays?|Deospray|body\s+sprays?)\b",
    r"\b(?:carb(?:urett?or)?|brake|contact)\s+cleaner\b", r"\b(?:Vergaser|Bremsen|Kontakt)reiniger\b",
    r"\b(?:polyester|epoxy|synthetic|liquid|casting|fib(?:re|er)glass)\s+resins?\b", r"\bresin\s+kits?\b",
    r"\b(?:Epoxid|Polyester|Gie[ßs])harz\w*", r"\bwood\s+(?:preservatives?|stains?)\b", r"\bHolzschutz\w*",
    r"\b(?:caustic\s+soda|sodium\s+hydroxide|potassium\s+hydroxide|Natriumhydroxid|Natronlauge|Kalilauge|"
    r"sodium\s+hypochlorite|Natriumhypochlorit|bleach(?:ing\s+agents?)?|Bleichmittel|Chlorbleiche|ammonia(?:\s+solution)?|"
    r"Ammoniak\w*|acetic\s+acid|Essigs[äa]ure|formic\s+acid|Ameisens[äa]ure)\b(?![- ]?(?:free|frei))",
    r"\b(?:calcium\s+hypochlorite|pool\s+chlorine|chlorine\s+(?:tablets|granules)|Chlortabletten|Poolchlor|"
    r"ammonium\s+nitrate|Ammoniumnitrat|potassium\s+permanganate|Kaliumpermanganat|sodium\s+chlorate|Natriumchlorat|"
    r"organic\s+peroxides?|organische\s+Peroxide|peroxides?)\b",
    r"\b(?:rodenticides?|cyanides?|Cyanid\w*|arsenic|pepper\s+sprays?|Pfefferspray\w*|tear\s+gas|Tr[äa]nengas|"
    r"Gefahrstoff\w*|ADR[- ]pflichtig)\b",
    r"\b(?:calcium\s+carbide|Calciumcarbid|sodium\s+metal|metallic\s+sodium|white\s+phosphorus|red\s+phosphorus|"
    r"phosphorus|(?:magnesium|aluminium|aluminum|zinc|titanium|metal)\s+(?:powders?|turnings|ribbons?|dust)|"
    r"(?:Magnesium|Aluminium|Zink|Titan|Metall)pulver|activated\s+(?:carbon|charcoal)|Aktivkohle|charcoal(?!\s*(?:gr[ae]y|colou?r|black|melange))|Holzkohle|"
    r"self[- ]heating)\b",
    r"\b(?:sparklers?|Wunderkerzen|(?:signal|distress|marine|hand)\s+flares?|Signalfackeln|Leuchtfackeln)\b",
    r"\b(?:life\s?rafts?|Rettungsinseln?|inflatable\s+life\s?(?:jackets?|vests?)|life\s?(?:jackets?|vests?)\s+with\s+CO2)\b",
    r"\b(?:sodium[- ]ion|Natrium[- ]Ionen|Na[- ]ion)(?:[- ]?(?:batter\w*|akku\w*|cells?))?\b",
    # Standalone batteries only: a product with its battery inside (laptops, phones, drones, cordless tools) is PI 967
    # Section II, no DGD: asking for one on every electronics RFQ would be wrong more often than right (Julien's xfail)
    r"\b(?:rechargeable\s+batter(?:y|ies)|spare\s+batter(?:y|ies)|battery\s+packs?|Akku-?[Pp]acks?|Akkus?(?![-\w])|Wechselakku\w*)\b",
    r"\b(?:electric\s+wheelchairs?|Elektrorollst[üu]hl\w*|mobility\s+scooters?|portable\s+power\s+stations?|"
    r"Powerstations?|solar\s+generators?)\b(?!\s*(?:bags?|cases?|covers?|parts|spare|accessor\w*|chargers?|cables?))",
    r"\b(?:biological|clinical|diagnostic|patient|blood|tissue|lab(?:oratory)?)\s+(?:samples?|specimens?)\b",
    r"\bcontaining\s+alcohol\b",
    r"\belectric\s+(?:skateboards?|unicycles?|golf\s+trolleys?|scooters?|bikes?)\b", r"\bgolf\s+trolleys?\s+with\s+batter",
    r"\bcarbon\s+dioxide\b(?!\s*(?:emissions?|footprint|neutral))",
    r"\bpool\s+chemicals?\b",
    r"\b(?:Blut|Patienten|Gewebe|Labor)proben\b", r"\bbiologische\s+Proben\b",
    r"\b(?:asbestos|Asbest|polymeric\s+beads|(?:expandable|expanded)\s+polystyrene\s+(?:beads|granulate)|EPS[- ]Granulat)\b",
    r"\b(?:motorcycles?|motorbikes?|Motorr[äa]der?|quad\s+bikes?|ATVs?|jet\s?skis?|snowmobiles?|"
    r"(?:used|new|complete|classic|vintage)\s+(?:cars?|vehicles?)|motor\s+vehicles?|passenger\s+cars?)\b"
    r"(?!\s*(?:parts|spare|helmets?|jackets?|gloves?|accessor\w*|covers?|tyres?|tires?|batteries\s+removed))",
    r"\b(?:(?:internal\s+)?combustion|petrol|gasoline|diesel|outboard|Verbrennungs|Au[ßs]enbord)[- ]?(?:engines?|motors?|motoren)\b"
    r"(?!\s*(?:parts|spare|oil|filters?|gaskets?|teile|ersatzteile))",
    r"\bengines?\s+with\s+(?:residual\s+)?fuel\b",
    r"\b(?:lawn\s?mowers?|Rasenm[äa]her\w*|chain\s?saws?|Kettens[äa]gen?|leaf\s+blowers?|Laubbl[äa]ser\w*|"
    r"pressure\s+washers?|Hochdruckreiniger\w*|(?:power|petrol|gasoline|diesel|portable)\s+generators?|"
    r"Stromerzeuger\w*|Notstromaggregat\w*|generator\s+sets?|gensets?)\b"
    r"(?!\s*(?:parts|spare|blades?|chains?|filters?|nozzles?|hoses?|teile|messer|ketten))",
)
# "Class 3" with nothing else: DG, unless the same line says what other kind of class it is
CLASS_ONLY = re.compile(r"\b(?:class|klasse|klase|classe|clase)\s*:?\s*[1-9](?:\.[1-6])?\b(?![.,]\d)", re.I)
NOT_DG_CLASS = re.compile(r"\b(?:ceramics?|Keramik\w*|porcelain|Porzellan|tiles?|Fliesen|concrete|Beton|strength|"
                          r"Festigkeit\w*|hardness|H[äa]rte\w*|abrasion|Abrieb\w*|Rutschhemm\w*|"
                          r"fire\s+(?:rating|resistance)|Brandschutz\w*|"
                          r"ISO|laser|medical|medizin\w*|device|Medizinprodukt\w*|clean\s*room|Reinraum\w*|protection|"
                          r"Schutz\w*|energy|efficiency|Effizienz\w*|insulation|IP\s?\d|accuracy|freight\s+class|NMFC|"
                          r"business|economy|first|truck|vehicle|LKW|Fahrzeug\w*|hotel|star|Sterne|"
                          r"tolerance|Toleranz|quality|grade|Güte\w*|seats?|cabin|travel|flight\s+class)\b", re.I)
# A clause ends at punctuation or a word that starts a new statement ("not stackable and contains dry ice").
_CLAUSE = re.compile(r"[.;!?\n:,()\[\]|]|\b(?:but|however|although|though|except|apart\s+from|and|or|contains?|containing|"
                     r"includ\w*|with|plus|also|aber|jedoch|sondern|allerdings|au[ßs]er|und|oder|enth[äa]lt\w*|inkl\w*|mit|"
                     r"mais|sauf|et|ou|avec|contient|pero|excepto|salvo|con|contiene|però|tranne|ma|ancak|fakat|maar)\b",
                     re.I)
_NEG_AFTER = re.compile(
    r"\s*(?:[(\[]\s*)?(?:[:=?–—]|-\s)\s*\|?\s*(?:no|none|nein|non|nil|n/?a|not\s+(?:applicable|restricted|included)|keine?s?|"
    r"nicht|false|nope|aucune?|ninguna?|nessuna?|geen|nee|nie|yok|hay[ıi]r|-|0)(?![\w])"
    r"|[\s-]+(?:free|frei)\b"
    r"|\s*\(?\s*(?:without|ohne|sans|sin|senza|excl\w*\.?|exkl\w*\.?)\s*(?:\w+\s+){0,2}(?:batter\w*|akku\w*|accu\w*|pile\w*)"
    r"|\s+(?:is|are|was|were|will\s+be|ist|sind|wird|werden|liegt|liegen|est|sont|son|è|sono|zijn|jest)\s+(?:\w+\s+)?"
    r"(?:not|nicht|keine?|pas|no|non|niet|nie)\s+(?:\w+\s+)?(?:included|contained|present|required|needed|used|part|"
    r"applicable|enthalten|vorhanden|erforderlich|ben[öo]tigt|dabei|vor|Teil|inclus\w*|incluid\w*|presente?s?|"
    r"necessari\w*|n[ée]cessaire\w*|requis\w*)\b"
    r"|\s+(?:not|nicht)\s+(?:included|enthalten|required|erforderlich|needed|ben[öo]tigt|present|vorhanden|applicable|"
    r"zutreffend|relevant)\b"
    r"|\s+(?:\w+\s+)?(?:de[ğg]il\w*|yok\w*|i[çc]ermez\w*)", re.I)
# Before the hit, a negation counts only when it governs it (Julien's review of #143): "no / without / kein / ohne / non /
# sans / sin / senza ..." with at most two words between, none a preposition or the noun the "no" is about ("no rush
# for the spray cans", "No idea whether the glue ...", "No other cargo besides the aerosols"); "not / nicht / pas"
# right before it ("not dangerous goods", "nicht um Gefahrgut", "pas de ..."); a negated copula ("No son ...", "Il ne
# s'agit pas de ..."). "Please don't stack the lithium batteries", "never shipped perfumes", "Not urgent dry ice" are DG.
_NEG_DET = (r"(?:no|without|free\s+of|kein\w*|ohne|non|none\s+of(?:\s+the)?|neither|nor|weder|noch|aucune?s?|sans|sin|"
            r"ning[uú]n[oa]?|ninguna|nessun[oa]?|senza|geen|zonder|bez|nem|pas\s+d[e'’]|pas\s+des)")
_NEG_ADV = r"(?:not|nicht|pas|niet|n[ãa]o)"
_NEG_COPULA = (r"(?:(?:is|are|was|were)(?:\s+not|n[’']t)|(?:ist|sind|war|waren)\s+(?:kein\w*|nicht)|"
               r"handelt\s+(?:es\s+)?sich\s+(?:\w+\s+)?nicht\s+um|ne\s+(?:sont|est)\s+pas|n[’']est\s+pas|"
               r"ne\s+s[’']agit\s+pas\s+d[e'’]?|no\s+(?:son|es|est[áa]n?)|non\s+(?:sono|è|e)|"
               r"not\s+(?:classified|regulated|declared|considered|shipped)\s+as)")
_GAP_STOP = (r"(?:for|of|to|about|besides|beside|regarding|whether|if|than|as|at|in|on|from|by|für|von|über|zu|wegen|"
             r"als|ob|pour|para|per|rush|hurry|idea|need|needed|required|problem|issue|doubt|pickup|insurance|stacking|"
             r"experience|change|urgent|eilig)")
_GOVERNS = re.compile(
    rf"(?:(?<![\w-]){_NEG_DET}\s+(?:(?!{_GAP_STOP}\b)[\w’'-]+\s+){{0,2}}"
    rf"|(?<![\w-]){_NEG_ADV}\s+(?:(?:a|an|any|the|um|de|des|du|d[e'’]|als)\s+)?"
    rf"|(?<![\w-]){_NEG_COPULA}\s+(?:(?:a|an|any|the|des|de|d[e'’]|um)\s+)?(?:[\w-]+\s+)?"
    rf"|(?<![\w-])(?:non|nicht|kein)-)$", re.I)
_LIST_GAP = re.compile(r"[\s,/&+]*(?:(?:and|or|nor|und|oder|noch|et|ou|ni|y|o|e|n[ée]|ve|veya)\b[\s,]*)?"
                       r"(?:(?:any|other|the|die|der|des|les|los|las|i|gli|le)\s+)?", re.I)
# Words that look like cargo words but aren't (V2 only): prices that are "frozen", device specs in °C.
FALSE_FRIENDS = re.compile(r"(?:price|rate|tariff|budget|cost|quote|offer)s?\s+(?:\w+\s+){0,2}frozen|"
                           r"frozen\s+(?:price|rate|tariff|budget|cost|quote|offer|account|pipe)s?|price\s+freeze|"
                           r"(?:operating|working|rated|design|storage\s+of\s+the\s+device)\s+temperature[^.\n]{0,40}|"
                           r"(?:temperature|heat)[- ]resistant[^.\n]{0,30}|resistant\s+(?:up\s+)?to\s+[+-]?\d+\s*°\s?C|"
                           r"Betriebstemperatur[^.\n]{0,40}|temperaturbest[äa]ndig[^.\n]{0,30}|"
                           r"(?:flash|melting|boiling)\s*point[^.\n]{0,30}|(?:Flamm|Schmelz|Siede)punkt[^.\n]{0,30}|"
                           r"chilled\s+water\s+\w+|jewell?e?ry\s+(?:boxes|box|displays?|stands?|trays?|cases?|packaging)|"
                           r"seafood\s+(?:processing|machines?|equipment)", re.I)
_TEMP = r"(?:°\s?C|degrees?\s+C(?:elsius)?|degrees?|Grad(?:\s+C(?:elsius)?)?|°|(?<=\d)\s?C\b)"
SPECIAL_V2 = {  # code → pattern; level and sentences as in SPECIAL
    "temperature": _TERMS(
        r"temperature[- ]?(?:controlled|control|sensitive|regulated|managed)", r"\bcold[- ]chain\b", r"\bcool[- ]chain\b",
        r"\brefrigerated\b", r"\brefrigeration\s+(?:required|needed)\b", r"\brequires?\s+refrigeration\b", r"\breefer\b",
        r"\bdeep[- ]?frozen\b", r"\bfrozen\b", r"\bchilled\b", r"\bkeep\s+(?:cool|cold|refrigerated|frozen|chilled)\b",
        r"\bdo\s+not\s+freeze\b", r"\bprotect\s+from\s+(?:heat|freezing|frost)\b",
        r"\btemperature\s+(?:data\s+)?loggers?\b", r"\b(?:with|incl\.?|including|plus)\s+(?:a\s+)?data[- ]?loggers?\b",
        r"\bEnvirotainer\b", r"\bactive\s+(?:temperature\s+)?containers?\b", r"\bvaccines?\b", r"\bImpfstoff\w*",
        r"\binsulin\b", r"\btemperature\s+(?:range|requirements?)\b", r"\bTemperaturbereich\b",
        rf"(?<![\d.,])[+-]?\d{{1,2}}(?:[.,]\d)?\s*{_TEMP}?\s*(?:-|–|—|/|to|and|bis|und|à|a|al|e|y|tot|ile)\s*"
        rf"[+-]?\d{{1,2}}(?:[.,]\d)?\s*{_TEMP}",
        r"(?<![\w.])\+\d{1,2}\s*(?:-|–|to|bis|/)\s*\+\d{1,2}\b",
        r"(?:\bat|\bbelow|\bunder|\bmax(?:imum)?\.?|\bnot\s+(?:above|exceeding|over)|\bunter(?:halb)?|\bbei|\bh[öo]chstens|"
        r"\bmaximal|\bmin(?:imum)?\.?|\bmindestens|\babove|\b[üu]ber|<|>|≤|≥)\s*[+-]?\d{1,2}(?:[.,]\d)?\s*"
        r"(?:°\s?C|degrees?(?:\s+C(?:elsius)?)?|Grad(?:\s+C(?:elsius)?)?)",
        r"(?<![\w.\d])-\s?\d{1,2}\s*°\s?C",
        r"\btemperaturgef[üu]hrt\w*", r"\btemperaturkontrolliert\w*", r"\bTemperaturf[üu]hrung\b", r"\bgek[üu]hlt\w*",
        r"\bK[üu]hlkette\b", r"\bK[üu]hlware\b", r"\bK[üu]hltransport\w*", r"\bK[üu]hlung\b", r"\btiefgek[üu]hlt\w*",
        r"\bTiefk[üu]hl\w*", r"\bk[üu]hl\s+(?:lagern|halten|transportieren)\b", r"\bnicht\s+einfrieren\b",
        r"\btemp[ée]rature\s+(?:dirig[ée]e|contr[ôo]l[ée]e|ma[îi]tris[ée]e)\b", r"\bcha[îi]ne\s+du\s+froid\b",
        r"\br[ée]frig[ée]r[ée]e?s?\b", r"\bsurgel[ée]e?s?\b", r"\bcongel[ée]e?s?\b",
        r"\btemperatura\s+(?:controlada|controllata|regulada|controlata)\b", r"\bcadena\s+de\s+fr[ií]o\b",
        r"\bcatena\s+del\s+freddo\b", r"\brefrigerad[oa]s?\b", r"\brefrigerat[oie]\b", r"\bcongelad[oa]s?\b",
        r"\bsurgelat[oie]\b", r"\bcongelat[oie]\b", r"\bso[ğg]uk\s+zincir\b", r"\bkoelketen\b", r"\bgekoeld\b"),
    "perishable": _TERMS(
        r"\bperishables?\b", r"\bfresh\s+(?:cut\s+)?(?:flowers|fish|meat|fruits?|produce|seafood|salmon|tuna|vegetables|"
        r"berries|herbs|cheese|dairy|poultry|mushrooms|asparagus|truffles)\b", r"\bseafood\b", r"\bcut\s+(?:flowers|roses)\b",
        r"\bfresh[- ]cut\s+\w+", r"(?<!artificial )(?<!silk )(?<!dried )(?<!plastic )(?<!paper )\bflowers\b"
        r"(?!\s*(?:pots?|vases?|stands?|holders?|baskets?|tubs?|planters?|boxes|seeds?|bulbs?|food|prints?|patterns?|"
        r"designs?|decorations?|arrangements?\s+\((?:artificial|silk)))",
        r"(?<!künstliche )(?<!getrocknete )\bBlumen\b", r"\bverderblich\w*", r"\bFrisch(?:fisch|fleisch|obst|gem[üu]se|ware)\w*",
        r"\bfrische[rnms]?\s+(?:Fisch|Fleisch|Obst|Gem[üu]se|Blumen|Lachs|Meeresfr[üu]chte)\b", r"\bSchnittblumen\b",
        r"\bMeeresfr[üu]chte\b", r"\bp[ée]rissables?\b", r"\bpoissons?\s+frais\b", r"\bproduits\s+frais\b",
        r"\bfleurs\s+(?:coup[ée]es|fra[îi]ches)\b", r"\bfruits\s+de\s+mer\b", r"\bperecederos?\b",
        r"\bpescados?\s+frescos?\b", r"\bflores\s+(?:cortadas|frescas)\b", r"\bmariscos\b", r"\bdeperibil[ei]\b",
        r"\bpesce\s+fresco\b", r"\bprodotti\s+freschi\b", r"\bfiori\s+(?:recisi|freschi)\b", r"\bfrutti\s+di\s+mare\b",
        r"\bbozulabilir\b", r"\bbederfelijk\w*"),
    "valuables": _TERMS(
        r"\bgold\s+(?:bars?|bullion|coins?|ingots?|granules|jewell?e?ry|dor[eé]|nuggets|bricks)\b", r"\bbullion\b",
        r"\bprecious\s+(?:metals?|stones?|gems?)\b", r"\bgemstones?\b", r"\bdiamonds\b", r"\bjewell?e?ry\b", r"\bjewels\b",
        r"\bbank\s?notes?\b", r"\bcurrency\s+notes\b",
        r"\bhigh[- ]value\s+(?:goods|cargo|shipments?|consignments?|items?|electronics|products?|watches|equipment|freight)\b",
        r"\bvaluable\s+(?:cargo|goods|shipments?|items?|freight)\b", r"\bvaluables\b", r"\bluxury\s+watches\b",
        r"\b(?:platinum|silver)\s+(?:bars?|bullion|ingots?)\b",
        r"\bWert(?:fracht|sendung\w*|sachen|gegenst[äa]nde)\b", r"\bSchmuck\b", r"\bJuwelen\b", r"\bGoldbarren\b",
        r"\bEdelmetall\w*", r"\bEdelsteine?\b", r"\bBanknoten\b", r"\bbijoux\b", r"\bjoaillerie\b", r"\blingots?\s+d'or\b",
        r"\bm[ée]taux\s+pr[ée]cieux\b", r"\bbillets\s+de\s+banque\b", r"\bmarchandises?\s+de\s+valeur\b", r"\bjoyas\b",
        r"\bjoyer[ií]a\b", r"\blingotes?\s+de\s+oro\b", r"\bmetales\s+preciosos\b", r"\bbilletes\s+de\s+banco\b", r"\bgioielli\b",
        r"\blingotti\s+d'oro\b", r"\bmetalli\s+preziosi\b", r"\bbanconote\b"),
    "non_stackable": _TERMS(
        r"non[- ]?stackable", r"not\s+stackable", r"do\s+not\s+(?:double[- ])?stack", r"\bno\s+stacking\b",
        r"\btop\s+load\s+only\b", r"\bno\s+top\s+load(?:ing)?\b", r"nicht\s+stapelbar", r"\bnicht\s+stapeln\b",
        r"\bStapeln\s+verboten\b", r"\bnon\s+(?:gerbable|empilable)s?\b", r"\bne\s+pas\s+(?:gerber|empiler)\b",
        r"\bno\s+apilables?\b", r"\bno\s+apilar\b", r"\bnon\s+(?:sovrapponibil|impilabil)[ei]\b"),
    "live_animals": _TERMS(
        r"\blive\s+(?:animals?|fish|birds|insects|lobsters?|crabs?|eels?|bees|horses?|dogs?|cats?|poultry|chicks|cattle|"
        r"sheep|pigs?|reptiles?|tropical\s+fish|ornamental\s+fish|shrimps?|oysters?|mussels|crayfish)\b",
        r"\b(?:fish|lobsters?|crabs?|animals?|birds|horses?|dogs?|cats?|insects)\s*\(\s*live\s*\)",
        r"\b(?:ornamental|aquarium|tropical)\s+fish\b(?!\s+(?:food|tanks?|nets?))", r"\bHaustiere?\b",
        r"\blivestock\b", r"\bhatching\s+eggs\b", r"\bday[- ]old\s+chicks\b", r"\brace\s?horses?\b", r"\bsport\s+horses?\b",
        r"\b(?-i:[Pp]et|[Dd]og|[Cc]at|[Hh]orse)\s+(?:transport|relocation|shipping|travel)\b",
        r"\b(?:\d+|two|three|four|a|an|our|my)\s+(?-i:dogs?|puppies|cats?|kittens|horses?)\b"
        r"(?!\s+(?:food|toys?|beds?|treats?|bowls?|leash\w*|collars?|saddles?|blankets?|figurines?|statues?|shampoo|litter|"
        r"trailers?|equipment))",
        r"\blebende[nr]?\s+(?:Tiere?|Fische|Hummer|Pferde|V[öo]gel|Bienen|Insekten)\b", r"\bTiertransport\w*",
        r"\bZierfische\b", r"\b(?:zwei|drei|vier|\d+)\s+(?:Hunde|Katzen|Pferde)\b", r"\banimaux\s+vivants\b",
        r"\banimales\s+vivos\b", r"\banimali\s+vivi\b", r"\bcanl[ıi]\s+hayvan\w*", r"\blevende\s+dieren\b",
        r"\b[żz]ywe\s+zwierz[ęe]ta\b"),
    "human_remains": _TERMS(
        r"\bhuman\s+remains\b", r"\bmortal\s+remains\b", r"\bcremated\s+remains\b", r"\bcremains\b", r"\bcoffins?\b",
        r"\b(?:funeral|burial)\s+caskets?\b", r"\brepatriation\s+of\s+(?:the\s+)?(?:body|deceased|remains)\b",
        r"\burns?\s+(?:with|containing)\s+(?:the\s+)?ashes\b", r"\bashes\s+of\s+(?:the\s+|my\s+|our\s+|his\s+|her\s+)?"
        r"(?:deceased|late|father|mother|husband|wife)\b", r"\bLeichnam\w*", r"\bSarg\b", r"\bS[äa]rge\b",
        r"\bUrne\s+mit\b", r"\bsterbliche\w*\s+[ÜU]berreste\b", r"\bd[ée]pouille\s+mortelle\b", r"\bcercueil\b",
        r"\brestos\s+mortales\b", r"\bata[úu]d\b", r"\bf[ée]retro\b", r"\b(?:la|una|della)\s+salma\b", r"\bresti\s+mortali\b"),
}
OVERSIZE = ("Some pieces are larger than lower-deck size, so they fly on a freighter's main deck: the airline confirms "
            "the space when we book.",
            "Einige Packstücke sind größer als das Unterdeck erlaubt und fliegen daher auf dem Hauptdeck eines "
            "Frachters: die Airline bestätigt den Platz bei der Buchung.")
HEAVY_PIECE_KG = 1500  # one piece above this needs a forklift slot and main-deck loading
LOWER_DECK_HEIGHT_CM, MAX_LENGTH_CM = 160, 300
# OVERSIZE_TEXT=off: sizes only from the extracted pieces, as before. On, also "L x W x H" written in the mail or an
# attachment (packing list): its dims never reach the pieces when the packing list's volume replaces them.
OVERSIZE_TEXT = os.environ.get("OVERSIZE_TEXT", "on").lower() != "off"
_UNIT = r"(?:cm|mm|m(?![\w³])|inch(?:es)?|in(?!\s*[A-Za-z])|zoll|\"|″|'')"
_NUM = r"\d+(?:[.,]\d+)*"
DIMS = re.compile(rf"(?<![\d.,/]){_NUM}(?:\s*{_UNIT})?(?:(?:\s*[x×X\*/]\s*|\s+by\s+){_NUM}(?:\s*{_UNIT})?){{2,3}}"
                  rf"(?![\d/])", re.I)
DIM_UNIT_BEFORE = re.compile(r"[(\[]\s*(cm|mm|m|in|inch(?:es)?)\s*[)\]]|\bin\s+(cm|mm|inch(?:es)?|met(?:er|re)s?)\b|"
                             r"\b(cm|mm)\b", re.I)
TO_CM = {"cm": 1.0, "mm": 0.1, "m": 100.0, "in": 2.54, "inch": 2.54, "inches": 2.54, "zoll": 2.54, '"': 2.54,
         "″": 2.54, "''": 2.54, "meter": 100.0, "meters": 100.0, "metre": 100.0, "metres": 100.0}


# A packing list's piece table, columns in any order (round 10: "Height (cm) | Gross weight (kg) | Width (cm) | Length
# (cm) | Pieces", round 11's PDF: "Pieces Length (cm) Height (cm) Width (cm) Gross weight (kg)").
_COLUMNS = (("pieces", r"pieces|pcs|qty|quantity|St[üu]ck\w*|Anzahl|Packst[üu]cke|colis|bultos|colli|pezzi"),
            ("length", r"length|l[äa]nge|longueur|largo|lunghezza"), ("width", r"width|breite|largeur|ancho|larghezza"),
            ("height", r"height|h[öo]he|hauteur|alto|altezza"), ("weight", r"(?:gross\s+)?weight|gewicht|poids|peso"))
COLUMN = re.compile("|".join(rf"(?P<{k}>\b(?:{p})\b)" for k, p in _COLUMNS), re.I)
COLUMN_UNIT = re.compile(r"[(\[]\s*(cm|mm|m|in|inch(?:es)?)\s*[)\]]", re.I)


def _table_pieces(lines: list[str]) -> list[tuple[float, float, float, float | None]]:
    from bids import to_number
    found = []
    for i, header in enumerate(lines):
        if "|" in header:
            cells = header.split("|")
            kinds = [next((k for k, v in m.groupdict().items() if v), None) if (m := COLUMN.search(c)) else None
                     for c in cells]
        else:
            cells, kinds = None, [next(k for k, v in m.groupdict().items() if v) for m in COLUMN.finditer(header)]
        if not {"length", "width", "height"} <= set(kinds) or len(kinds) != len(set(kinds) - {None}) + kinds.count(None):
            continue
        dims_at = min(header.lower().find(w) for w in ("length", "width", "height", "länge", "breite", "höhe",
                                                         "longueur", "largeur", "hauteur", "largo", "ancho", "alto",
                                                         "lunghezza", "larghezza", "altezza") if w in header.lower())
        unit = (COLUMN_UNIT.search(header, dims_at) or [None, None])[1]
        if not unit or unit.lower() not in TO_CM:
            continue
        for row in lines[i + 1:]:
            values = [c.strip() for c in row.split("|")] if cells else re.findall(_NUM, row)
            if len(values) != len(kinds) or not row.strip():
                break
            got = {k: to_number(v) for k, v in zip(kinds, values) if k}
            if any(got.get(k) is None or got[k] <= 0 for k in ("length", "width", "height")):
                break
            cm = [round(got[k] * TO_CM[unit.lower()], 1) for k in ("length", "width", "height")]
            pounds = 0.45359237 if re.search(r"[(\[]\s*lbs?\s*[)\]]", header, re.I) else 1.0
            each = got["weight"] * pounds / got["pieces"] if got.get("weight") and got.get("pieces") else None
            if all(1 <= c <= 2000 for c in cm):
                found.append((*cm, each))
    return found


# One size written with its name: "Height: 175 cm", "crate length 3.2 m", "175 cm high", "a 3.2 m long crate". Without a
# colon, the line start or a piece word next to it a length is a product's ("hose length 15 m", "a 15 m long hose").
_PIECE = r"(?:crates?|cases?|pallets?|pieces?|boxe?s?|cartons?|skids?|machines?|Kisten?|Paletten?|caisses?|colis|casse?)"
LABELLED = re.compile(rf"(?P<piece>\b{_PIECE}\s+)?\b(?P<key>height|h[öo]he|hauteur|altezza|length|l[äa]nge|longueur|"
                      rf"lunghezza)(?P<colon>\s*[:=])?\s*(?P<n>{_NUM})\s*(?P<u>{_UNIT})|(?P<n2>{_NUM})\s*(?P<u2>{_UNIT})"
                      rf"\s+(?P<key2>high|tall|hoch|long|lang)\b(?P<piece2>\s+{_PIECE}\b)?", re.I)
_PIECE_BEFORE = re.compile(rf"\b{_PIECE}\b(?:\s+\w+){{0,3}}\s*$", re.I)  # "the crate is | 3.2 m long"


def _labelled(lines: list[str]) -> list[tuple[float, float, float, float | None]]:
    from bids import to_number
    found = []
    for line in lines:
        for m in LABELLED.finditer(line):
            if m["key"] and not (m["colon"] or m["piece"] or not line[:m.start()].strip()):
                continue
            if m["key2"] and m["key2"].lower() in ("long", "lang") and not (
                    m["piece2"] or _PIECE_BEFORE.search(line[:m.start()])):
                continue
            key, n, unit = (m["key"], m["n"], m["u"]) if m["key"] else (m["key2"], m["n2"], m["u2"])
            value = to_number(n)
            if value is None or (unit or "").lower() not in TO_CM:
                continue
            cm = round(value * TO_CM[unit.lower()], 1)
            if 1 <= cm <= 2000:
                tall = key.lower()[:1] in "ha" or key.lower() == "tall"  # height/höhe/hauteur/altezza/high/hoch/tall
                found.append((0.0, 0.0, cm, None) if tall else (cm, 0.0, 0.0, None))
    return found


def text_dims(text: str) -> list[tuple[float, float, float, float | None]]:
    """Piece sizes in cm (length, width, height, kg per piece or None) written as "L x W x H unit" ("320 x 120 x 175 cm",
    "126 x 47 x 69 in", "3200x1200x1750 mm", "4 x 120x80x170 cm": four numbers = count first) or as a packing-list
    table. A size without a unit is skipped: inches read as cm hide a tall piece, cm read as inches invent one."""
    from bids import to_number  # money parser: "1.200" (mm) is 1200, "1,20" (m) is 1.2
    lines, found = (text or "").splitlines(), []
    for i, line in enumerate(lines):
        for m in DIMS.finditer(line):
            parts = re.findall(rf"({_NUM})\s*({_UNIT})?", m.group(0), re.I)
            units = [u.lower() for _, u in parts if u]
            above = next((l for l in lines[i - 1::-1] if l.strip()), "") if i else ""  # a table header: "Dims (cm)"
            hint = DIM_UNIT_BEFORE.findall(line[max(0, m.start() - 40):m.start()]) or DIM_UNIT_BEFORE.findall(above)
            unit = units[-1] if units else next((u.lower() for pair in hint[::-1] for u in pair if u), None)
            numbers = [to_number(n) for n, _ in parts]
            if len(numbers) == 4:
                numbers = numbers[1:]  # "4 x 120 x 80 x 170 cm": 4 pieces
            if unit not in TO_CM or any(n is None or n <= 0 for n in numbers):
                continue
            cm = [round(n * TO_CM[unit], 1) for n in numbers]
            if all(1 <= c <= 2000 for c in cm):
                found.append((*cm, None))
    return found + _table_pieces(lines) + _labelled(lines)


# PRICE_SANITY_V2=off: section 5 as before (pickup leg, below half the median of three or more, zero). On, also:
# - two options: the chosen one below half of the other (a per-piece price read as the total);
# - the chosen one more than GATE_HIGH_RATIO × the median of the others (a surcharge or the weight counted twice,
#   R15 too_high): the kit's sheets differ by at most 1.81× on one lane, so twice the median is never a real price;
# - per chargeable kg far outside anything the kit charges (bids-only lanes have no other option to compare with);
# - a pickup leg dearer than the flight, a breakdown that doesn't add up to the total or counts a surcharge twice;
# - pickup words in the mail ("EXW our plant", "pickup from our warehouse") but no pickup read (R1 too_low).
# Review of #143 (fewer wrong holds, each costs the 240 s wait):
# - fastest asked and the fastest option chosen: no median check (fastest is often dearer), the per-kg ceiling stays;
# - "door-to-door", DAP/DDP are delivery at destination (shapes.DESTINATION_DELIVERY says so), never a pickup; and when
#   the shipper brings the goods to the airport ("we bring it to FRA", "wir liefern an den Flughafen") none is expected.
PRICE_SANITY_V2 = os.environ.get("PRICE_SANITY_V2", "on").lower() != "off"
HIGH_RATIO = float(os.environ.get("GATE_HIGH_RATIO", "2.0"))
CEILING_EUR_PER_KG, CEILING_MIN_EUR = 25.0, 450.0  # 3 × the kit's dearest all-in rate (7.88/kg) and minimum (145)
FLOOR_EUR_PER_KG = 0.7  # below half the kit's cheapest all-in rate (1.65/kg at 2,000 kg+)
PICKUP_CEILING_EUR = 400.0  # kit truckers bid about 45-250 EUR per zone
CBM_KG = 167
DOOR_WORDS = _TERMS(
    r"\b(?:EXW|ex[- ]works|ab\s+Werk|franco\s+fabbrica|d[ée]part\s+usine|en\s+f[áa]brica)\b",
    r"\bdoor[- ]to[- ](?:airport|port)\b", r"\btruck(?:ing)?\s+(?:pick[- ]?up|collection)\b",
    r"\b(?:pick[- ]?up|collect(?:ion)?)\s+(?:from|at)\s+(?:our|the\s+(?:shipper|supplier|seller|factory|plant|warehouse))\b",
    r"\bAbholung\s+(?:bei|ab|von|in)\s+(?:uns|unserem|unserer|unseres)\b", r"\bab\s+(?:unserem|unserer)\s+(?:Lager|Werk|Halle|Standort)\b",
    r"\b(?:bei|ab)\s+uns\s+(?:\w+\s+){0,3}?abholen\b", r"\b(?:bei|ab)\s+uns\s+(?:\w+\s+){0,3}?abzuholen\b",
    r"\benl[èe]vement\s+(?:chez|dans)\s+(?:nous|notre)\b", r"\brecogida\s+en\s+(?:nuestr[oa]s?)\b",
    r"\britiro\s+(?:presso|dal|dalla)\s+(?:noi|nostr[oa])\b")
_AIRPORT = rf"(?:airport|Flughafen|a[ée]roport|aeropuerto|aeroporto|terminal|cargo\s*(?:center|centre|city|hub)|" \
           rf"{'|'.join(sorted(shapes.ORIGINS))})"
SELF_DELIVERY = _TERMS(  # the shipper brings the goods to the origin airport: no pickup expected
    rf"\b(?:we|I|the\s+shipper|our\s+(?:own\s+)?(?:driver|truck|trucker|haulier|carrier|forwarder))\s+(?:will\s+|can\s+|"
    rf"shall\s+|would\s+|'ll\s+|are\s+going\s+to\s+)?(?:bring|deliver|drop|take|truck|haul|send)\w*\b[^.\n]{{0,60}}?"
    rf"\b(?:to|at|into)\s+(?:the\s+|your\s+)?(?:[\w-]+\s+){{0,2}}?{_AIRPORT}\b",
    r"\b(?:we|I)\s+(?:will\s+|can\s+|'ll\s+)?deliver\s+(?:it\s+|them\s+|the\s+(?:goods|cargo|shipment)\s+)?ourselves\b",
    r"\bself[- ]deliver\w*", r"\bdelivered\s+by\s+(?:us|ourselves|the\s+shipper)\b",
    r"\b(?:delivered|brought|dropped\s+off)\s+(?:\w+\s+){0,3}?by\s+(?:us|ourselves|the\s+shipper|our\s+(?:own\s+)?"
    r"(?:truck|driver|haulier|trucker))\b",
    r"\b(?:delivered|brought|dropped\s+off)\s+(?:to|at)\s+your\s+(?:[\w-]+\s+){0,3}?(?:warehouse|terminal|hub|station|shed)\b",
    rf"\b(?:wir|ich)\s+(?:\w+\s+){{0,3}}?(?:liefern|bringen|stellen|fahren)\b[^.\n]{{0,60}}?\b(?:{_AIRPORT}|"
    rf"Ihr\w*\s+(?:\w+\s+)?(?:Lager|Halle|Station))",
    rf"\b(?:liefern|bringen)\s+(?:wir|ich)\b[^.\n]{{0,60}}?\b(?:{_AIRPORT}|Ihr\w*\s+(?:\w+\s+)?(?:Lager|Halle))",
    rf"\banliefer\w*\b[^.\n]{{0,30}}?\b(?:am|an\s+den|an|zum|beim|bei)\s+(?:\w+\s+)?{_AIRPORT}",
    r"\bAnlieferung\s+durch\s+(?:uns|den\s+Versender)\b", r"\bselbst\s+an(?:geliefert|liefern|zuliefern)\b",
    r"\b(?:wird|werden)\s+(?:\w+\s+){0,4}?(?:von|durch)\s+uns\s+(?:\w+\s+){0,3}?(?:angeliefert|geliefert|gebracht)\b",
    r"\bSelbstanlieferung\b")
_SAYS_NOT = re.compile(r"\b(?:not|nicht|kein\w*|never|nie|cannot)\b|n't", re.I)


def _self_delivery(text: str) -> re.Match | None:
    return next((m for m in _hits(SELF_DELIVERY, text) if not _SAYS_NOT.search(m.group(0))), None)


def _chargeable(rfq: dict) -> float | None:
    """max(actual kg, cbm × 167) of the request, like the backend; None without a weight."""
    pieces = rfq.get("pieces") or []
    actual = sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in pieces)
    if pieces and all(p.get("length_cm") and p.get("width_cm") and p.get("height_cm") for p in pieces):
        cbm = sum((p.get("count") or 1) * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in pieces) / 1e6
    else:
        cbm = rfq.get("volume_m3") or 0
    return max(actual, cbm * CBM_KG) or None


def _breakdown_issue(option: dict) -> str | None:
    lines = [line for line in option.get("breakdown") or [] if isinstance(line, dict) and line.get("amount") is not None]
    if not lines:
        return None
    total = sum(float(line["amount"]) for line in lines)
    if abs(total - float(option["total"])) > 0.05 + 0.001 * float(option["total"]):
        return f"the breakdown adds up to EUR {total:,.2f}, the total says EUR {float(option['total']):,.2f}"
    for word in ("Fuel", "Security", "Pickup"):
        if sum(str(line.get("label") or "").startswith(word) for line in lines) > 1:
            return f"{word.lower()} is in the breakdown twice"
    return None


# Words that also name a packing-list column or heading. A bare label claims nothing when the list answers no to it:
# "Dangerous goods | No", a heading "Dangerous goods" over "None", a column "Item | Dangerous goods | Gross weight" over
# "1 | No | 715" (a blank or "-" cell is a no too). Any other answer ("Yes", "5 kg", "Lithium batteries") is a claim,
# and so is the same word in a value cell ("Description: | Dry ice", "1 | Lithium batteries | 4").
LABEL = re.compile(r"dangerous\s+\w+|hazardous\s+\w+|haz[- ]?mat|Gefahrg[uü]t\w*|gef[äa]hrliche\w*\s+G[üu]ter|"
                   r"mati[èe]res?\s+dangereuses?|marchandises?\s+dangereuses?|mercanc[ií]as?\s+peligrosas?|"
                   r"merci\s+pericolose|perishables?|temperature[- ]?\w+|valuables|non[- ]?stackable|not\s+stackable|"
                   r"live\s+animals?|human\s+remains|lithium(?:[- ]\w+)?|dry\s*ice|Trockeneis", re.I)
_CELL_END = re.compile(r"[ \t]*(?:\(\s*y(?:es)?\s*/\s*no?\s*\)[ \t]*)?(?:\||\n|$)", re.I)
_NO_CELL = re.compile(r"\s*(?:no|none|nein|keine?|non|aucune?|nil|n/?a|ninguna?|nessuna?|nee|geen|nie|hay[ıi]r|yok|"
                      r"false|0|[-–—]+|not\s+applicable|nicht\s+zutreffend|entf[äa]llt)?\s*\.?\s*", re.I)


def _label(text: str, m: re.Match) -> bool:
    if not LABEL.fullmatch(m.group(0)) or not (end := _CELL_END.match(text, m.end())):
        return False
    line_start, line_end = text.rfind("\n", 0, m.start()) + 1, text.find("\n", m.end())
    line_end = len(text) if line_end < 0 else line_end
    prefix = text[line_start:m.start()]
    rest = text[end.end() - 1:line_end] if text[end.end() - 1:end.end()] == "|" else ""  # "| next cell | …"
    below = text[line_end + 1:].split("\n")
    if prefix.strip() and not re.search(r"(?<!:)(?<!:\s)\|\s*$", prefix):
        return False  # inside a sentence or a value cell
    if not prefix.strip() and not rest:  # a heading: the next line answers
        return _NO_CELL.fullmatch(next((line for line in below if line.strip()), "x")) is not None
    if not prefix.strip() and _NO_CELL.fullmatch(rest.split("|")[1]):
        return True  # a row label: "Dangerous goods | No"
    column, width = prefix.count("|"), (prefix + rest).count("|")  # a column header: every row below says no
    cells = []
    for line in below:
        if line.count("|") != width:
            break
        cells.append(line.split("|")[column])
    return bool(cells) and all(_NO_CELL.fullmatch(c) for c in cells)


def _negated(text: str, m: re.Match, after_negated: int | None) -> bool:
    """Is this hit said not to apply? See CARGO_WORDS_V2."""
    if after_negated is not None and _LIST_GAP.fullmatch(text[after_negated:m.start()]):
        return True  # "no aerosols, perfumes or lithium batteries"
    if _label(text, m):
        return True
    clause = _CLAUSE.split(text[max(0, m.start() - 80):m.start()])[-1]
    if _GOVERNS.search(" ".join(clause.split()) + (" " if clause[-1:].isspace() else "")):
        return True
    return bool(_NEG_AFTER.match(text, m.end()))


# Hits that name something else, not the goods (review of #143). No negation either, so a list goes on being read:
# - a reference number: "Our ref: UN 2024", "PO UN-4711", "Rechnung UN1234";
# - the packaging, not its contents: "empty perfume bottles", "aerosol caps (plastic, empty)", "leere Spraydosen",
#   "Spraydosen-Deckel", "nozzles for spray cans". A filled one ("perfume, 50 ml bottles") is DG.
UN_HIT = re.compile(r"(?:UN|U\.N\.|ONU|un)(?![A-Za-z])")
REF_BEFORE = re.compile(r"\b(?:ref(?:erence)?|Referenz|Bezug|order|PO|P\.O\.|purchase\s+order|invoice|Rechnung|Auftrag|"
                        r"Bestellung|Bestell)(?:s?(?:nummer|nr|no))?\.?\s*(?:no\.?|nr\.?|number|nummer|#)?\s*[:#.-]?\s*$",
                        re.I)
CONTAINABLE = re.compile(r"aerosol|a[ée]rosol|spray|spr[üu]h|druckgas|perfum|parf|fragranc|eau\s+de|profum|duft|paint|"
                         r"varnish|lacquer|polish|lack|peinture|vernis|pintura|barni|vernic|ink|druckfarb|stain|"
                         r"adhesive|glue|kleb|solvent|sanitizer|ethanol|alcohol|isopropanol|pesticide|insecticide|"
                         r"herbicide|ammunition|munition|extinguisher|l[öo]scher|cylinder|gas", re.I)
# Equipment for the goods, not the goods (Julien's review): "paint shop equipment", "fire extinguisher brackets",
# "oxygen cylinder regulators", "car battery chargers", "isotope analyzers", "hand sanitizer dispensers", "spare parts
# for e-bikes", "Lithium Holdings Ltd". "Li-ion tools", "lithium battery packs / systems" stay DG.
EQUIPMENT_AFTER = re.compile(
    r"[\s-]*(?:shops?|equipment|brackets?|holders?|mounts?|regulators?|chargers?|dispensers?|analy[sz]ers?|sprayers?|"
    r"detectors?|testers?|gauges?|cabinets?|lockers?|stands?|racks?|signs?|labels?|stickers?|manuals?|training|"
    r"courses?|software|accessor(?:y|ies)|spare\s+parts|booths?|guns?|brush(?:es)?|rollers?|Halter\w*|Ladeger[äa]te?|"
    r"Zubeh[öo]r|Ersatzteile|Schr[äa]nke?|Etiketten|Schulung\w*|Regler|Pr[üu]fger[äa]te?)\b", re.I)
COMPANY_AFTER = re.compile(r"\s+(?:Holdings?|Ltd\b|Limited|Inc\b|Corp\w*|GmbH|AG\b|plc\b|LLC\b|S\.A\.|Company|"
                           r"Mining|Resources|Group|Industries|Technologies)", re.I)
FOR_BEFORE = re.compile(r"\b(?:spare\s+parts|parts|accessor(?:y|ies)|equipment|tools?|brackets?|holders?|mounts?|"
                        r"chargers?|cases?|covers?|Ersatzteile|Zubeh[öo]r|Teile|Halter(?:ungen)?|Ladeger[äa]te?)\s+"
                        r"(?:for|für|f\.|pour|para|per)\s+(?:the\s+|die\s+|den\s+|les\s+)?(?:[\w-]+\s+)?$", re.I)
CARTRIDGE_AFTER = re.compile(r"[\s-]*(?:cartridges?|Patronen|toner)\b", re.I)
_MATERIAL = r"(?:glass|Glas|plastic|Kunststoff|PET|alu\w*|metal|Metall|tin|new|neue?[nm]?|small|kleine?[nm]?|\d+[.,]?\d*\s*ml)"
_EMPTY = r"(?:empty|emptied|leer|unfilled|ungef[üu]llt|vides?|vac[ií][oa]s?|vuot[eio])"
_PART = (r"(?:caps?|Kappen?|lids?|Deckel|nozzles?|D[üu]sen?|valves?|Ventile?|actuators?|closures?|Verschl[üu]ss\w*|"
         r"packaging|Verpackung(?:en)?|bouchons?|capuchons?|tapas?|tappi)")
EMPTY_BEFORE = re.compile(rf"\b{_EMPTY}(?:e[nmrs]?)?\s+(?:{_MATERIAL}\s+){{0,2}}$", re.I)
PART_BEFORE = re.compile(rf"\b{_PART}\s+(?:for|für|f\.|of|von|pour|para|per)\s+(?:the\s+|die\s+|den\s+|les\s+)?"
                         rf"(?:(?:{_MATERIAL}|{_EMPTY}\w*)\s+){{0,2}}$", re.I)
PART_IN = re.compile(r"(?:deckel|kappen?|d[üu]sen?|ventile?|verpackung(?:en)?|verschl[üu]ss\w*)$", re.I)  # compounds
PART_AFTER = re.compile(rf"[\s,(-]*(?:(?:spray\s+)?(?:bottles?|cans?|containers?|flacons?|Flaschen|Flakons?|Dosen?|tins?|"
                        rf"jars?|Tiegel|boxes|cases|Kisten|cylinders?)[\s,(-]*)?(?:{_MATERIAL}\s*,?\s*)*"
                        rf"(?:{_PART}\b|{_EMPTY})", re.I)


def _not_the_goods(text: str, m: re.Match) -> bool:
    hit, line, after = m.group(0), text[text.rfind("\n", 0, m.start()) + 1:m.start()], text[m.end():m.end() + 80]
    if UN_HIT.match(hit):
        return bool(REF_BEFORE.search(line))
    if EQUIPMENT_AFTER.match(after) or COMPANY_AFTER.match(after) or FOR_BEFORE.search(line):
        return True
    if re.search(r"ink|toner", hit, re.I) and CARTRIDGE_AFTER.match(after):
        return True  # "printing ink cartridges"
    if CONTAINABLE.search(hit):
        return bool(EMPTY_BEFORE.search(line) or PART_BEFORE.search(line) or PART_IN.search(hit)
                    or PART_AFTER.match(text, m.end()))
    return False


def _hits(pattern: re.Pattern, text: str):
    """The hits of pattern in text that no negation takes back, in order."""
    negated_end = None
    for m in pattern.finditer(text):
        if _not_the_goods(text, m):
            continue
        if _negated(text, m, negated_end):
            negated_end = m.end()
        else:
            negated_end = None
            yield m


def _first_hit(pattern: re.Pattern, text: str) -> re.Match | None:
    return next(_hits(pattern, text), None)


def _class_hit(text: str) -> re.Match | None:
    """A bare "Class 9" / "Klasse 3": DG unless its line names another kind of class (ISO, laser, medical device, …)."""
    for m in CLASS_ONLY.finditer(text):
        start, end = text.rfind("\n", 0, m.start()) + 1, text.find("\n", m.end())
        if NOT_DG_CLASS.search(text[start:end if end >= 0 else len(text)]) or _negated(text, m, None):
            continue
        return m
    return None
INJECTION = re.compile(r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+instructions|"
                       r"system\s+prompt|you\s+are\s+(?:an?\s+)?(?:AI|language\s+model|assistant)|"
                       r"disregard\s+(?:your|the)\s+(?:rules|instructions)", re.I)

# ---- constraints next to "cheapest" / "fastest" ---------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                          "dec"))} | {"mär": 3, "mai": 5, "okt": 10, "dez": 12}
# DEADLINE_FORMATS=off: only the formats above (ISO, 28.11.2026, 28 November 2026, November 28, 2026; English/German).
# On: also 28/11/2026, a date without the year ("November 28", "28.11.") and Italian/Spanish/French/Dutch/Polish words.
DEADLINE_FORMATS = os.environ.get("DEADLINE_FORMATS", "on").lower() != "off"
if DEADLINE_FORMATS:
    MONTHS |= {"gen": 1, "ene": 1, "fév": 2, "fev": 2, "abr": 4, "avr": 4, "mag": 5, "giu": 6, "juil": 7, "juin": 6, "lug": 7,
               "ago": 8, "aoû": 8, "aou": 8, "set": 9, "ott": 10, "déc": 12, "dic": 12}
    _YEAR = r"(?:,?\s+\d{4})?"
    _DATE = (r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\.\d{1,2}\.(?!\d)|"
             r"\d{1,2}(?:st|nd|rd|th|er)?\.?\s+(?:of\s+)?[^\W\d_]{3,}\.?" + _YEAR + r"|"
             r"[^\W\d_]{3,}\.?\s+\d{1,2}(?:st|nd|rd|th)?\b" + _YEAR + r")")
    _OTHER = (r"|(?:entro\s+(?:e\s+non\s+oltre\s+)?(?:il\s+)?|a\s+m[aá]s\s+tardar\s+(?:el\s+)?|au\s+plus\s+tard\s+(?:le\s+)?|"
              r"uiterlijk\s+(?:op\s+)?|najp[oó][źz]niej\s+(?:do\s+)?)" + _DATE)
else:
    _DATE = (r"(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-zä]{3,}\.?\s+\d{4}|"
             r"[A-Za-z]{3,}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})")
    _OTHER = ""
DEADLINE = re.compile(r"(?:arrive|arrival|delivered|delivery|be\s+(?:in|at)\s+\w+|land|there|needed|need\s+it|required)"
                      r"[^.\n]{0,40}?(?:by|before|no\s+later\s+than|latest(?:\s+by)?|until|on\s+or\s+before)\s+"
                      r"(?:the\s+)?" + _DATE + r"|(?:spätestens|bis\s+(?:zum|spätestens))\s+(?:am\s+)?" + _DATE + _OTHER,
                      re.I)
# BUDGET_SPACES (on): "EUR 1 800" (space) and Swiss "1'800 EUR" were read as a budget of EUR 1, so every quote was held
# as over budget; "2k EUR" was not read. A thousands group is exactly three digits after a space, apostrophe, dot or comma.
BUDGET_SPACES = os.environ.get("BUDGET_SPACES", "on").lower() != "off"
_AMOUNT = (r"(\d{1,3}(?:[ '.,]\d{3})+(?:[.,]\d{1,2})?(?![\d])|\d+(?:[.,]\d+)?(?:\s?[kK]\b)?)" if BUDGET_SPACES
           else r"(\d[\d.,]*)")
BUDGET = re.compile(r"(?:budget(?:\s+is)?|max(?:imum)?|under|below|no\s+more\s+than|not\s+(?:more|above)\s+than|"
                    r"up\s+to|höchstens|maximal|unter)\s+(?:of\s+)?(?:EUR|€)\s?" + _AMOUNT + r"", re.I)
# BUDGET_FORMATS: also the amount before the currency ("our budget is 2.000 EUR", "max. 2,000 EUR all-in") and "max."
# with a dot. off: only "budget/max/under ... EUR 2,000".
BUDGET_FORMATS = os.environ.get("BUDGET_FORMATS", "on").lower() != "off"
BUDGET_AFTER = re.compile(r"(?:budget(?:\s+is|\s+of)?|max(?:imum|\.)?|under|below|no\s+more\s+than|not\s+(?:more|above)"
                          r"\s+than|up\s+to|höchstens|maximal|unter|within)\s*:?\s*(?:of\s+)?(?:(?:EUR|€)\s?" + _AMOUNT + r"|"
                          + _AMOUNT + r"(?:[.,]-{1,2})?\s?(?:EUR|€|euros?)(?![\w/]))", re.I)  # "2.000,- EUR"
# QUOTE_CURRENCY: "please quote in USD" → the quote is written in USD at the rate the portal states (backend "fx", EUR
# per 1 unit; FX_FALLBACK if the portal never stated one). Only the mail itself counts, never a packing list's "value in
# USD". off = the old hold: a person decides, the EUR quote goes out.
QUOTE_CURRENCY = os.environ.get("QUOTE_CURRENCY", "on").lower() != "off"
_CUR = (r"(USD|US[\s-]*dollars?|dollars?|CHF|Swiss\s+francs?|Schweizer\s+Franken|GBP|pounds?\s+sterling|"
        r"britischen?\s+Pfund)")
# Only an explicit request for our quote (review of #125): a request verb ("please quote in USD", "can you price this in
# USD", "send your offer in US dollars"), the quote itself ("quotation in CHF", "Angebot bitte in CHF"), or
# "prices/rates in X please". Never "item price in USD: 45" or "our offer in USD to the end client was 50k".
ASKED_CURRENCY = re.compile(
    r"(?:\b(?:please|kindly|pls|can\s+you|could\s+you|would\s+you|bitte)\s+(?:also\s+|just\s+)?(?:quote|price)\s+"
    r"(?:us\s+|it\s+|this\s+|the\s+shipment\s+)?(?:all-in\s+)?|"
    r"\b(?:send|give)\s+(?:us\s+)?(?:your|the|a)\s+(?:quote|quotation|offer)\s+|"
    # the bare noun only at the start of the sentence or after "please / we need …" ("Quotation in USD please",
    # "Bitte das Angebot in CHF"), never "the supplier's quote in USD was too high"
    r"(?:^\s*|\b(?:please|kindly|bitte|we\s+need|we\s+require|we['’]d\s+like|we\s+would\s+like|wir\s+brauchen|"
    r"wir\s+benötigen)\s+)(?:send\s+)?(?:your\s+|the\s+|a\s+|das\s+|ihr\s+|bitte\s+)?(?:quotation|quote|angebot)\s+"
    r"(?:please\s+|bitte\s+)?)"
    r"in\s+" + _CUR + r"\b(?!\s*[\d$€£])"  # an amount right after ("in USD 12,400"); "quote in USD: 3 pieces" asks
    r"|\b(?:quotation|quote|angebot)\s+in\s+" + _CUR.replace("(", "(?P<cur3>", 1) + r"\s*,?\s*(?:please|bitte|:)"
    r"|\b(?:prices|rates|preise)\s+in\s+" + _CUR.replace("(", "(?P<cur2>", 1) + r"\s+(?:please|bitte)\b", re.I)
# A sentence about the goods or their value, an amount, EUR named too, or a negation: never a request for the quote
# currency.
NOT_ASKED = re.compile(r"\b(?:value|invoice|customs|goods|unit|item|product|purchase|article|commodity|insurance|insured|"
                       r"declared|end\s+client|per\s+(?:piece|item|unit)|wert|warenwert|rechnung|zoll|artikel|stück|"
                       r"ware|EUR|euros?)\b|€|\b(?:not|never|don'?t|no\s+need|nicht|kein\w*)\b[^.!?\n]{0,20}"
                       r"\b(?:in\s+)?(?:USD|CHF|GBP|dollars?|francs?|franken|pfund)\b|"
                       r"\b(?:not|never)\s+(?:be\s+)?accept\w*|nicht\s+akzeptiert|"
                       # someone else's quote: "the supplier's quote in USD", "our quote in USD to the client"
                       r"\b(?:our|their|his|her|last|previous|earlier|old|other|another|competitor\w*|supplier\w*|"
                       r"forwarder\w*|vendor\w*|client\w*|lieferant\w*|konkurren\w*|wettbewerb\w*)(?:['’]s)?\s+"
                       r"(?:\w+(?:['’]s)?\s+){0,2}?(?:quote|quotation|offer|angebot)\b|['’]s\s+(?:quote|quotation|offer)\b|"
                       r"\b(?:competitor\w*|konkurren\w*|wettbewerb\w*|was|were|war|waren)\b", re.I)


def asked_currency(text: str) -> str | None:
    """USD / CHF / GBP when the customer explicitly asks for our quote in it, else None."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if (m := ASKED_CURRENCY.search(sentence)) and not NOT_ASKED.search(sentence):
            return _currency(m.group(1) or m.group("cur2") or m.group("cur3"))
    return None


OTHER_CURRENCY = re.compile(r"\b(?:in|price\s+in|quote\s+in|prices?\s+in|all-in\s+\w*\s*in)\s+"
                            r"(USD|US\s*dollars?|CHF|Swiss\s+francs?|GBP|pounds?\s+sterling)\b", re.I)


def _currency(word: str) -> str:
    w = word.lower()
    return "CHF" if ("chf" in w or "fran" in w) else "GBP" if ("gbp" in w or "pound" in w or "pfund" in w) else "USD"


def _finding(code: str, level: str, text: str) -> dict:
    return {"code": code, "level": level, "text": text}


def _parse_date(text: str, year: int | None = None) -> date | None:
    """A date as the customer wrote it. year: for a date without one ("November 28", "28.11.")."""
    text = text.strip().rstrip(",")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text):
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            return date(y, int(m[2]), int(m[1]))
        if not DEADLINE_FORMATS:
            text = text.rstrip(".")
        if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-zä]{3,})\.?\s+(\d{4})", text):
            return date(int(m[3]), MONTHS[m[2][:3].lower()], int(m[1]))
        if m := re.fullmatch(r"([A-Za-z]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", text):
            return date(int(m[3]), MONTHS[m[1][:3].lower()], int(m[2]))
        if not DEADLINE_FORMATS:
            return None
        text = text.rstrip(".") if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.", text) else text
        if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text):  # Europe: day first, unless that can't be
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            first, second = int(m[1]), int(m[2])
            return date(y, second, first) if second <= 12 else date(y, first, second)
        if year is None:
            return None
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.", text):
            return date(year, int(m[2]), int(m[1]))
        if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th|er)?\.?\s+(?:of\s+)?([^\W\d_]{3,})\.?(?:,?\s+(\d{4}))?", text):
            return date(int(m[3] or year), MONTHS[m[2][:3].lower()], int(m[1]))
        if m := re.fullmatch(r"([^\W\d_]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", text):
            return date(int(m[3] or year), MONTHS[m[1][:3].lower()], int(m[2]))
    except (KeyError, ValueError):
        return None
    return None


def deadline(text: str, after: date | None = None) -> date | None:
    """The latest arrival date the customer names ("must arrive by 2026-11-30", "spätestens am 30.11.2026").

    after: the ready date; a date written without a year is the first one on or after it.
    """
    for m in DEADLINE.finditer(text):
        raw = next(g for g in m.groups() if g)
        year = after.year if after else None
        found = _parse_date(raw, year)
        if found and after and year and not re.search(r"\d{4}", raw) and found < after:
            found = _parse_date(raw, year + 1)  # "by January 5" asked in November
        if found and (after is None or found > after):  # on or before the ready date: a deadline for our quote
            return found
    return None


def budget(text: str) -> float | None:
    if (m := BUDGET.search(text)) or (BUDGET_FORMATS and (m := BUDGET_AFTER.search(text))):
        raw = next(g for g in m.groups() if g).rstrip(".,")
        thousand = 1
        if BUDGET_SPACES:
            raw = raw.replace(" ", "").replace("'", "")
            if raw[-1:] in "kK":
                raw, thousand = raw[:-1].strip(), 1000
        if re.search(r"[.,]\d{3}$", raw) or re.search(r"[.,]\d{3}[.,]", raw):  # 3.000 / 3,000 / 3.000,00
            raw = re.sub(r"[.,](?=\d{3}\b)", "", raw)
        try:
            return float(raw.replace(",", ".")) * thousand
        except ValueError:
            return None
    return None


def _arrives(option: dict, ready: date | None) -> date | None:
    if ready is None or option.get("transit_days") is None:
        return None
    return ready + timedelta(days=-(-float(option["transit_days"]) // 1))  # whole days, rounded up


def _ready(rfq: dict) -> date | None:
    try:
        return date.fromisoformat(rfq.get("ready_date") or "")
    except ValueError:
        return None


def _pick(options: list[dict], ask: str | None) -> dict:
    """The same rule as the backend: fastest → fewest days, ties cheaper; else cheapest, ties faster."""
    slow = max((o["transit_days"] for o in options if o.get("transit_days") is not None), default=99)
    days = lambda o: o["transit_days"] if o.get("transit_days") is not None else slow  # noqa: E731
    if ask == "fastest":
        return min(options, key=lambda o: (days(o), o["total"]))
    return min(options, key=lambda o: (o["total"], days(o)))


def _same(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in ("source", "carrier", "rate_id", "total"))


# ---- the review ---------------------------------------------------------------------------------------------------

def review(rfq: dict, result: dict, mail: dict, texts: list[str] | tuple = (), elapsed_s: float | None = None) -> dict:
    """Checks a priced request before the quote is written.

    rfq / result: the Rfq and the /api/price response. texts: readable attachment texts (packing list, SLI).
    Returns {"chosen": option to quote, "sentences": extra sentences for the quote, "findings": [...], "hold": bool}.
    In warn mode the findings are the same, but chosen, sentences and hold are never changed.
    """
    chosen, options = result.get("chosen"), [o for o in result.get("options") or [] if o.get("total") is not None]
    out = {"chosen": chosen, "sentences": [], "findings": [], "hold": False}
    if MODE == "off" or not chosen:
        return out
    request = "\n".join([mail.get("subject") or "", mail.get("body") or "", *[t for t in texts if t]])
    clean = NEGATED.sub(" ", request)
    found = out["findings"]
    lang = ((rfq.get("language") or "en")[:2]).lower()
    say = lambda en, de: de if lang == "de" else en  # noqa: E731

    # V2: attachment names count as text too ("Lithium_Battery_Declaration.pdf" that no reader can open)
    names = [re.sub(r"_+", " ", os.path.splitext(a.get("filename") or "")[0]) for a in mail.get("attachments") or []]
    scan = "\n".join([request, *names]) if CARGO_WORDS_V2 else clean

    # 1. Dangerous goods the other checks don't know (dry ice, corrosive, …): the template asks for the papers.
    if not rfq.get("dangerous_goods") and (m := (_first_hit(DG_V2, scan) or _class_hit(scan)) if CARGO_WORDS_V2
                                           else DG_EXTRA.search(clean)):
        rfq["dangerous_goods"], rfq["dg_declared"] = True, m.group(0)
        found.append(_finding("dangerous_goods", "fix", f"Dangerous goods ({m.group(0)}): the quote asks for the DG papers"))

    # 2. Special cargo: one sentence the customer expects, or a person for what we can't book blind.
    special = FALSE_FRIENDS.sub(" ", scan) if CARGO_WORDS_V2 else clean
    for code, pattern, level, en, de in SPECIAL:
        if m := (_first_hit(SPECIAL_V2.get(code, pattern), special) if CARGO_WORDS_V2 else pattern.search(clean)):
            found.append(_finding(code, level, f"{code.replace('_', ' ')} ({m.group(0).strip()})"))
            if level == "fix":
                out["sentences"].append(say(en, de))

    # 3. Piece sizes from the request: main deck needed?
    pieces = rfq.get("pieces") or []
    tall = any((p.get("height_cm") or 0) > LOWER_DECK_HEIGHT_CM for p in pieces)
    long_ = any(max(p.get("length_cm") or 0, p.get("width_cm") or 0) > MAX_LENGTH_CM for p in pieces)
    heavy = any((p.get("weight_kg") or 0) > HEAVY_PIECE_KG for p in pieces)
    written = [d for d in text_dims(request) if d[2] > LOWER_DECK_HEIGHT_CM or max(d[:2]) > MAX_LENGTH_CM
               or (d[3] or 0) > HEAVY_PIECE_KG] if OVERSIZE_TEXT and not (tall or long_ or heavy) else []
    if tall or long_ or heavy or written:
        size = f" (written: {' x '.join(f'{c:g}' if c else '?' for c in written[0][:3])} cm)" if written else ""
        found.append(_finding("oversize", "fix", f"Piece too tall, long or heavy for the lower deck{size}"))
        out["sentences"].append(say(*OVERSIZE))

    # 4. Constraints next to the ask: arrival deadline and budget narrow the options before the pick.
    feasible, ready = options or [chosen], _ready(rfq)
    if constraints.ON:  # carriers the customer excludes or requires, a maximum transit time (round 42), before deadline and budget
        feasible, more = constraints.narrow(rfq, feasible)
        found += [_finding(*f) for f in more]
    if (by := deadline(request, ready)) and ready:
        ok = [o for o in feasible if (_arrives(o, ready) or date.max) <= by]
        if ok:
            feasible = ok
            found.append(_finding("deadline", "note", f"Must arrive by {by}: {len(ok)} of {len(options)} options do"))
        else:
            found.append(_finding("deadline", "hold", f"Must arrive by {by}: no option arrives in time"))
    if (cap := budget(request)) is not None:
        ok = [o for o in feasible if o["total"] <= cap]
        if ok:
            feasible = ok
        else:
            found.append(_finding("budget", "note", f"Budget EUR {cap:,.2f}: no option is within it"))
    narrowed = len(feasible) < len(options or [chosen])
    pick = _pick(feasible, rfq.get("ask")) if feasible else chosen
    bids_only = all(o.get("source") == "carrier_bid" for o in options)  # the backend picks those 50/50 on purpose
    if narrowed and not _same(pick, chosen) and not any(_same(o, chosen) for o in feasible):
        found.append(_finding("constraint", "fix", f"{pick['carrier']} EUR {pick['total']:,.2f} meets the customer's "
                                                    f"constraint ({chosen['carrier']} doesn't)"))
        chosen = pick
    elif rfq.get("ask") == "fastest" and not bids_only and not _same(pick, chosen) and \
            (pick.get("transit_days") or 99) < (chosen.get("transit_days") or 99):
        found.append(_finding("ask", "fix", f"Fastest asked: {pick['carrier']} ({pick['transit_days']:g} d) is faster "
                                            f"than {chosen['carrier']}"))
        chosen = pick

    # 5. Price sanity: door-to-port must include the trucker (round 1 too_low); a far-too-cheap total misses a part.
    if rfq.get("pickup") and not chosen.get("pickup"):
        found.append(_finding("pickup_missing", "hold", "Door-to-port, but the price has no pickup leg (too_low risk)"))
    totals = [o["total"] for o in options]
    if len(totals) >= 3 and chosen["total"] < OUTLIER_RATIO * statistics.median(totals):
        found.append(_finding("too_low", "hold", f"EUR {chosen['total']:,.2f} is below {OUTLIER_RATIO:.0%} of the "
                                                 f"median EUR {statistics.median(totals):,.2f}: a part may be missing"))
    if chosen["total"] <= 0:
        found.append(_finding("zero_price", "hold", "The total is zero or negative"))
    if PRICE_SANITY_V2:
        found += _price_sanity(rfq, chosen, options, scan)

    for warning in result.get("warnings") or []:  # the backend's price guard (/api/price "warnings", PR #64)
        found.append(_finding("price_warning", "note", str(warning)))

    # 6. Currency, scope, tampering, time.
    code = asked_currency(f"{mail.get('subject') or ''}\n{mail.get('body') or ''}") if QUOTE_CURRENCY else None
    if code and (rate := (result.get("fx") or {}).get(code)) and chosen.get("currency", "EUR") == "EUR":
        eur = chosen["total"]
        chosen = {**chosen, "currency": code, "total": round(eur / float(rate), 2), "total_eur": eur,
                  "fx_eur_per_unit": float(rate)}
        found.append(_finding("currency", "fix", f"Customer asks for {code}: EUR {eur:,.2f} quoted as {code} "
                                                 f"{chosen['total']:,.2f} at {float(rate):g} EUR/{code}"))
    elif m := OTHER_CURRENCY.search(request):
        found.append(_finding("currency", "hold", f"Customer asks for a price in {m.group(1)}; we quote EUR"))
    if INJECTION.search(request):
        found.append(_finding("injection", "note", "The mail tries to give us instructions; prices still come from code"))
    if elapsed_s is not None and elapsed_s > 330:
        found.append(_finding("late", "note", f"{elapsed_s:.0f} s after the RFQ: the window closes at 360 s"))

    # 7. Shapes one amount must answer in words: delivery at destination, cheapest and fastest (shapes.py).
    in_eur = {**chosen, "total": chosen.get("total_eur", chosen["total"])}  # options are in EUR (QUOTE_CURRENCY)
    for finding, sentence in shapes.gate_sentences(rfq, mail, texts, options or [chosen], in_eur, lang, budget(request)):
        found.append(finding)
        out["sentences"].append(sentence)

    if MODE == "warn":
        return {**out, "chosen": result["chosen"], "sentences": [], "hold": False}
    return {**out, "chosen": chosen, "hold": any(f["level"] == "hold" for f in found)}


def _price_sanity(rfq: dict, chosen: dict, options: list[dict], text: str) -> list[dict]:
    """PRICE_SANITY_V2: totals that a part missing or counted twice explains (R1 too_low, R15 too_high)."""
    found, total = [], float(chosen["total"])
    others = [float(o["total"]) for o in options if not _same(o, chosen)]
    if len(options) == 2 and others and total < OUTLIER_RATIO * others[0]:
        found.append(_finding("too_low", "hold", f"EUR {total:,.2f} is below {OUTLIER_RATIO:.0%} of the other option's "
                                                 f"EUR {others[0]:,.2f}: a part may be missing"))
    fastest = rfq.get("ask") == "fastest" and all((chosen.get("transit_days") or 99) <= (o.get("transit_days") or 99)
                                                   for o in options)
    if others and total > HIGH_RATIO * statistics.median(others) and not fastest:
        found.append(_finding("too_high", "hold", f"EUR {total:,.2f} is above {HIGH_RATIO:g} × the other options' median "
                                                  f"EUR {statistics.median(others):,.2f}: a part may be counted twice"))
    pickup = float((chosen.get("pickup") or {}).get("total") or 0)
    air, kg = total - pickup, chosen.get("chargeable_weight_kg") or _chargeable(rfq)  # the weight it was priced on
    if kg and air > max(CEILING_MIN_EUR, CEILING_EUR_PER_KG * kg):
        found.append(_finding("too_high", "hold", f"EUR {air / kg:,.2f} per chargeable kg for the flight: far above any "
                                                  "kit rate (a per-kg price multiplied twice?)"))
    if kg and air < FLOOR_EUR_PER_KG * kg and not any(o.get("source") in ("sheet", "portal") for o in options):
        found.append(_finding("too_low", "hold", f"EUR {air / kg:,.2f} per chargeable kg for the flight: far below any "
                                                 "kit rate (a per-piece or per-kg price read as the total?)"))
    if pickup > max(PICKUP_CEILING_EUR, air):
        found.append(_finding("too_high", "hold", f"The pickup (EUR {pickup:,.2f}) costs more than the flight"))
    if issue := _breakdown_issue(chosen):
        found.append(_finding("breakdown", "hold", f"Price breakdown: {issue}"))
    if not rfq.get("pickup") and (m := _first_hit(DOOR_WORDS, text)) and not _self_delivery(text):
        found.append(_finding("pickup_unread", "hold", f"The mail asks for a pickup ({m.group(0)}), but the price has "
                                                       "none (too_low risk)"))
    return found


def finish(text: str, verdict: dict, rfq: dict) -> tuple[str, list[dict]]:
    """Puts the gate's sentences into the written quote and checks the mail itself. Returns (text, new findings)."""
    found = []
    if verdict["sentences"] and MODE != "warn":
        parts = text.split("\n\n")
        at = 2 if len(parts) > 3 else len(parts) - 1  # after the offer paragraph, before the price
        text = "\n\n".join(parts[:at] + [" ".join(verdict["sentences"])] + parts[at:])
    amounts, chosen = MONEY.findall(text), verdict["chosen"]
    if amounts != [f"{chosen['total']:,.2f}"]:
        found.append(_finding("amounts", "hold", f"The mail should state one amount, it states {amounts}"))
    if chosen.get("currency") and chosen["currency"] not in text:
        found.append(_finding("currency_missing", "hold", "The mail doesn't name the currency"))
    if rfq.get("dangerous_goods") and not re.search(r"MSDS|Dangerous Goods|Gefahrgut|DG", text):
        found.append(_finding("dg_papers", "hold", "Dangerous goods, but the mail doesn't ask for the DG papers"))
    return text, found


def summary(findings: list[dict]) -> str:
    return "; ".join(f"{f['level'].upper()} {f['text']}" for f in findings)

