# HUMAN_MAILS_FINAL.md: the "between" customer mails, Julien's base plus Ulas's add-ons (for Orhun)

> Ulas, Sun 22 Nov ~02:30. One page for everything about the human-sounding mails: what to do now, why, what Julien built, what was added on top, how every language reads today, what is still left. All mail text is written by code from fixed templates. No LLM writes or rewrites a mail.

## 1. Do this now (the live agent still sends the old wording)

Checked on the live UI at 02:27 (sessions 103–105, `quote_sent` events). Live runs Julien's between style, but **an older version**:

> Hello Jonas Kessler,
>
> thank you for your request. For your **10 pieces of textile samples** I can offer Solace Air Cargo from Stuttgart (STR) to Melbourne (MEL) for EUR 6,008.30 all in, pickup included. **We'd collect tuesday** and they should land around 29 Nov, about 4 days.

Everything below is **already merged into `main`** (PR #255 → `6518dfe`, PR #257 → `4e49677`). Only the live process is behind.

1. On the one live machine: `git fetch origin && git status`. Make sure the checked-out branch contains the code: `git merge-base --is-ancestor 4e49677 HEAD && echo ok`. If it doesn't, `git pull origin main` (or merge `main` into the live branch).
2. Check that `.env` doesn't set `QUOTE_STYLE` to anything other than `between`. Unset means `between`, which is the default since #238.
3. Restart `make live` right after a quote has gone out (RFQs come every 6 min). On start, the worker picks up RFQs that were still being priced.
4. Check the next `quote_sent` in the UI. It should read "If that works for you, we can collect …" and name the weight ("your 450 kg of …") when the customer gave no packing word.

**If pushing to main wasn't OK:** both merges are plain merge commits and come out cleanly with `git revert -m 1 4e49677` and then `git revert -m 1 6518dfe`. For an instant switch without a deploy, set `QUOTE_STYLE=short|a|classic` in `.env` and restart.

## 2. Why this matters (humanity points)

Data from `/v1/board/me` (`points.humanity`):
- We won humanity in rounds 13 and 19 (old templates), and in **55, 57, 58, 64 and 74 while `QUOTE_STYLE=a` was the default** (18:32–22:41).
- We won it **0 times in about 16 rounds after `short` became the default** at 22:41.
- Humanity goes to roughly one team per round.

What the real sent mails showed:
- **`short`:** so terse it reads like a bot. The same lines repeat in every mail, plus the stock "Thanks again for thinking of us."
- **`a`:** reacted to *this* customer (small talk returned, goods, town, days), but was long and stiff ("I've put together a quote for your request", "Your all-in price is …", full "Wednesday 25 November" dates, a 3-line signature).
- **`a` also had a bug:** it turned pieces into items, e.g. "your four maintenance spray cans".

The 5U rule: a reader must not be able to tell a machine wrote it. Small imperfections are fine.

**between** sits in the middle: short and casual like `short`, personal like `a`. The design rule is human-first: the human mail *is* the template, and code fills the slots.

## 3. Julien's base (PR #238, merged)

- **The `QUOTE_STYLE` switch** in `agent/quote_style.py`: `between` (default), `short`, `a`, `b`, `classic`, `human`. You can switch back without a deploy.
- **`short_mail.between_quote`**, a slot template:
  `{greeting}` / `{small-talk reply, only if they wrote some}` `{offer: goods, airline, city names, amount, pickup town}` `{plan: pickup day, arrival "around" a day, days in transit}` / `{DG papers line, only if DG}` / `{reply line}` / `{short sign-off}`.
- **Reused from `humanizer.py` (style a):**
  - small-talk detection and its one-line reply
  - greeting rules: formal "Hello Ms Weber" only when the customer wrote that title, otherwise "Hello Anna Weber"
  - pickup town
  - city names next to the codes ("Frankfurt (FRA)")
  - day names
- **Reused from `short_mail.py`:**
  - the length (3–5 lines)
  - casual wording
  - "cheers, / Lena"
  - per-language templates with placeholders, facts filled by code
- **Booked, airline-confirmed and tracking mails** use the same voice: "done, it's booked with …", "… just confirmed BK-…, so you're all set."
- **Unchanged guards:**
  - exactly one amount per quote (`gate.MONEY`, any `d.dd` number counts)
  - the DG papers request
  - all gate checks
  - reply in the customer's language
  - never ISO dates, never German "du"
- **PR #245 (Julien, on top of my first add-ons):** formal-sender and small-talk detection also for French/Spanish/Italian/Dutch/Portuguese/Turkish ("Cordialement", "Atentamente", "Geachte", "Saygılarımla", "comment allez-vous"). Before, only English/German markers counted.

## 4. Ulas's add-ons (all in `agent/short_mail.py`, tests in `agent/test_between_style.py`)

**a) More languages (#245):**
- between in fr/es/it/nl/pt/tr: offer, pickup, plan, DG, reply, sign-off, booked and confirmed mails.
- Goods names with any letter (Turkish goods were being dropped).
- The plan sentence starts with a capital.
- Turkish dates use month names ("30 Kasım"), because "29.11" would count as a second amount.

**b) Turkish with real verbs (#255):**
- Before: "her şey dahil, Frankfurt alımı dahil." (no verb, robotic).
- Now: "… Frankfurt alımı ve her şey dahil toplamda EUR 1,308.21 tutuyor. Size de uyarsa perşembe günü alabiliriz, 29 Kasım civarı da varır. Kısa bir cevap yeterli, rezervasyonu yaparım, yer ise sonra onaylanır."
- The DG and booking lines use the same tone.

**c) Offer instead of announce, in every language (#255).** The plan sentence asks instead of stating. The reply line follows the Turkish model: "a short reply is enough, I'll book, the space is confirmed afterwards".

| | before | now |
|---|---|---|
| en | We'd collect thursday … | If that works for you, we can collect thursday … |
| de | Wir holen am Donnerstag ab … | Wenn es Ihnen passt, holen wir am Donnerstag ab … |
| fr | On enlève jeudi … | Si ça vous convient, on peut passer chercher la marchandise jeudi … |
| es | Recogemos el jueves … | Si le va bien, podemos pasar a recoger la mercancía el jueves … |
| it | Ritiriamo giovedì … | Se le va bene, possiamo passare a ritirare giovedì … |
| nl | We halen donderdag op … | Als het u uitkomt, kunnen we het donderdag komen ophalen … |
| pt | Recolhemos quinta-feira … | Se lhe der jeito, podemos fazer a recolha na quinta-feira … |
| tr | perşembe alıyoruz | Size de uyarsa perşembe günü alabiliriz |

**d) One register per mail, and native details (#255):**
- **Greetings and sign-offs that match the formal "you":**
  - Italian "Buongiorno" (not "Ciao" next to "Lei").
  - Dutch "Hallo … Groeten" (not "Hoi … groetjes" next to "u").
  - Portuguese "Cumprimentos" (not "abraço").
- **French elision:** "d'aérosols", never "de aérosols".
- **Portuguese:** "na quinta-feira", "no sábado".
- **Italian:** "rif. PO-883:", not "per il suo riferimento PO-883: per i suoi …".
- **Turkish:** "cumartesi civarı", not "cumartesi günü civarı".
- The DG paragraph starts with a capital.
- No repeated pickup noun in one sentence (fr/es/nl).

**e) Goods: the weight instead of "pieces" (#257).**
- If the customer wrote no packing word (e.g. "3 pcs" or dimensions only), the quote names the weight:
  - "your 450 kg of machine parts", or "your 450 kg shipment" when the goods are generic
  - "Ihre 450 kg Maschinenteile"
  - "vos 450 kg d'aérosols"
  - "450 kg makine parçası" (before: "3 parça makine parçası")
- The weight is rounded to whole kg so the one-amount check never sees a `.50`.
- If they did write one, it comes back as they wrote it: "your 3 crates of …".

**f) The customer's packing word, in their language (#257):**
- "i suoi 8 pallet", "as suas 8 paletes", "sus 3 cajas", "uw 3 dozen", "3 sandık".
- Before, every customer got colli/volumes/bultos.
- `PACKING` now also recognises palettes/paletes/palés/bancali, caisses/casse/caixotes/sandık, cajas/scatole/caixas/dozen/koli, fûts/bidones/fusti/vaten/tambores/varil.

**g) A formal plan sentence for formal senders (#257):**

| | formal sentence |
|---|---|
| fr | Si cela vous convient, nous pouvons passer chercher la marchandise jeudi et l'envoi devrait arriver vers le 30/11 |
| es | Si le parece bien … |
| it | Se per Lei va bene … |
| nl | Als het u schikt … |
| pt | Se lhe for conveniente … |
| tr | Uygun görürseniz … |

English and German use one sentence for both.

**h) Capitals after the greeting and in the sign-off, fr/es/nl/pt/tr (#257).** "Bonjour Claire,\n\nPour vos …", "Cordialement,", "Görüşmek üzere,". Lowercase there reads like a template or a non-native writer. English lowercase is the deliberate casual touch. German ("Hallo Jürgen,\n\nfür Ihre …") and Italian are correct as they are.

## 5. Rules every mail keeps

- **One amount per quote,** written by code. No other `d.dd` number: dates are day names or "30/11" / "30 Kasım", weights are whole kg.
- **No ISO dates,** also in tracking ("handover is monday", never 2026-11-24).
- **Never "your 1 piece",** and never goods turned into items ("four spray cans").
- **A title only if the customer wrote it,** never German "du", and one register per mail.
- **The DG papers request** whenever DG is detected. "your packing list declares" only if the DG info really came from a packing list.
- **Same voice for the reply line, booked, confirmed and tracking mails.** The first reply in a thread is always the quote.

## 6. How it reads now (rendered from `main` at `4e49677`, `QUOTE_STYLE=between`)

### en

**Casual, door pickup, no packing word (weight)**
> Hi Anna,
>
> all good here, thanks, hope yours is too! For your 450 kg of machine parts I can do Solace Air Cargo from Frankfurt (FRA) to New York (JFK) for EUR 1,308.21 all in, pickup in Bad Homburg included. If that works for you, we can collect thursday and they should land around 30 Nov, about 3 days.
>
> just reply and I'll book it, space gets confirmed then.
>
> cheers,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Hello Ms Weber,
>
> thank you for your request. Fastest I've got for your 8 pallets of spray cans is Solace Air Cargo from Frankfurt (FRA) to New York (JFK), EUR 1,308.21 all in. If that works for you, they can fly friday and land around 30 Nov, about 3 days.
>
> these are dangerous goods, so I'll need the Shipper's Declaration for Dangerous Goods and the MSDS from you before pickup.
>
> just reply and I'll book it, space is confirmed at booking.
>
> best regards,
> Lena

**Booked**
> Hi Anna,
>
> done, it's booked with Solace Air Cargo, FRA to JFK, ref BK-1A2B3C4D. I'll let you know as soon as they confirm.
>
> cheers,
> Lena

**Airline confirmed**
> Hi Anna,
>
> Solace Air Cargo just confirmed BK-1A2B3C4D, so you're all set.
>
> cheers,
> Lena

### de

**Casual, door pickup, no packing word (weight)**
> Hallo Jürgen,
>
> danke, hier ist alles gut, ich hoffe bei Ihnen auch! Für Ihre 450 kg Maschinenteile kann ich Solace Air Cargo von Frankfurt (FRA) nach New York (JFK) anbieten, EUR 1,308.21 all-in, Abholung in Bad Homburg inklusive. Wenn es Ihnen passt, holen wir am Donnerstag ab, Ankunft etwa am 30. November (ca. 3 Tage).
>
> Kurzes Ja reicht, dann buche ich, der Platz wird bei der Buchung bestätigt.
>
> viele Grüße
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Guten Tag Anna Weber,
>
> vielen Dank für Ihre Anfrage. Am schnellsten geht es für Ihre 8 Paletten Spraydosen mit Solace Air Cargo von Frankfurt (FRA) nach New York (JFK), EUR 1,308.21 all-in. Wenn es Ihnen passt, geht es am Freitag los, Ankunft etwa am 30. November (ca. 3 Tage).
>
> Da es Gefahrgut ist, brauche ich vor der Abholung die Shipper's Declaration for Dangerous Goods und das Sicherheitsdatenblatt (MSDS) von Ihnen.
>
> Eine kurze Antwort genügt, dann buche ich, der Platz wird bei der Buchung bestätigt.
>
> freundliche Grüße
> Lena

**Booked**
> Hallo Jürgen,
>
> erledigt, ist gebucht bei Solace Air Cargo, FRA nach JFK, Buchungsnummer BK-1A2B3C4D. Ich melde mich, sobald die Airline bestätigt.
>
> viele Grüße
> Lena

**Airline confirmed**
> Hallo Jürgen,
>
> Solace Air Cargo hat BK-1A2B3C4D gerade bestätigt, damit ist alles startklar.
>
> viele Grüße
> Lena

### fr

**Casual, door pickup, no packing word (weight)**
> Bonjour Claire,
>
> Pour vos 450 kg de pièces de machine, je peux vous proposer Solace Air Cargo de Frankfurt (FRA) à New York (JFK) pour EUR 1,308.21 tout compris, enlèvement à Bad Homburg inclus. Si ça vous convient, on peut passer chercher la marchandise jeudi et ça devrait arriver vers le 30/11.
>
> Une petite réponse suffit, je réserve et la place est confirmée ensuite.
>
> À bientôt,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Bonjour Claire Martin,
>
> Merci pour votre demande. Le plus rapide pour vos 8 palettes d'aérosols, c'est Solace Air Cargo de Frankfurt (FRA) à New York (JFK), EUR 1,308.21 tout compris. Si cela vous convient, l'envoi peut partir vendredi et arriver vers le 30/11.
>
> Ce sont des marchandises dangereuses, donc il me faut la Shipper's Declaration for Dangerous Goods et la FDS (MSDS) avant l'enlèvement.
>
> Une petite réponse suffit, je réserve et la place est confirmée ensuite.
>
> Cordialement,
> Lena

**Booked**
> Bonjour Claire,
>
> C'est fait, réservé avec Solace Air Cargo, FRA à JFK, réf. BK-1A2B3C4D. Je vous préviens dès qu'ils confirment.
>
> À bientôt,
> Lena

**Airline confirmed**
> Bonjour Claire,
>
> Solace Air Cargo vient de confirmer BK-1A2B3C4D, tout est prêt.
>
> À bientôt,
> Lena

### es

**Casual, door pickup, no packing word (weight)**
> Hola Lucía,
>
> Para sus 450 kg de piezas de maquinaria le puedo ofrecer Solace Air Cargo de Frankfurt (FRA) a New York (JFK) por EUR 1,308.21 todo incluido, recogida en Bad Homburg incluida. Si le va bien, podemos pasar a recoger la mercancía el jueves y debería llegar hacia el 30/11.
>
> Con una respuesta corta basta, lo reservo y el espacio se confirma después.
>
> Saludos,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Hola Lucía García,
>
> Gracias por su solicitud. Lo más rápido para sus 8 cajas de aerosoles es Solace Air Cargo de Frankfurt (FRA) a New York (JFK), EUR 1,308.21 todo incluido. Si le parece bien, puede salir el viernes y llegar hacia el 30/11.
>
> Son mercancías peligrosas, así que necesito la Shipper's Declaration for Dangerous Goods y la ficha de seguridad (MSDS) antes de la recogida.
>
> Con una respuesta corta basta, lo reservo y el espacio se confirma después.
>
> Un saludo cordial,
> Lena

**Booked**
> Hola Lucía,
>
> Hecho, reservado con Solace Air Cargo, FRA a JFK, ref. BK-1A2B3C4D. Le aviso en cuanto confirmen.
>
> Saludos,
> Lena

**Airline confirmed**
> Hola Lucía,
>
> Solace Air Cargo acaba de confirmar BK-1A2B3C4D, todo listo.
>
> Saludos,
> Lena

### it

**Casual, door pickup, no packing word (weight)**
> Buongiorno Marco,
>
> per i suoi 450 kg di parti di macchine posso proporle Solace Air Cargo da Frankfurt (FRA) a New York (JFK) a EUR 1,308.21 tutto incluso, ritiro a Bad Homburg incluso. Se le va bene, possiamo passare a ritirare giovedì e dovrebbe arrivare verso il 30/11.
>
> Basta una breve risposta, prenoto io e lo spazio viene confermato dopo.
>
> a presto,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Buongiorno Marco Rossi,
>
> grazie per la richiesta. Il più veloce per i suoi 8 pallet di bombolette spray è Solace Air Cargo da Frankfurt (FRA) a New York (JFK), EUR 1,308.21 tutto incluso. Se per Lei va bene, può partire venerdì e arrivare verso il 30/11.
>
> Sono merci pericolose, quindi mi servono la Shipper's Declaration for Dangerous Goods e la scheda di sicurezza (MSDS) prima del ritiro.
>
> Basta una breve risposta, prenoto io e lo spazio viene confermato dopo.
>
> cordiali saluti,
> Lena

**Booked**
> Buongiorno Marco,
>
> fatto, prenotato con Solace Air Cargo, FRA-JFK, rif. BK-1A2B3C4D. Le scrivo appena confermano.
>
> a presto,
> Lena

**Airline confirmed**
> Buongiorno Marco,
>
> Solace Air Cargo ha appena confermato BK-1A2B3C4D, è tutto a posto.
>
> a presto,
> Lena

### nl

**Casual, door pickup, no packing word (weight)**
> Hallo Sanne,
>
> Voor uw 450 kg machineonderdelen kan ik Solace Air Cargo aanbieden van Frankfurt (FRA) naar New York (JFK) voor EUR 1,308.21 all-in, ophalen in Bad Homburg inbegrepen. Als het u uitkomt, kunnen we het donderdag komen ophalen en het zou rond 30/11 moeten landen.
>
> Een kort antwoord is genoeg, dan boek ik het en wordt de plek daarna bevestigd.
>
> Groeten,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Beste Jan de Vries,
>
> Bedankt voor uw aanvraag. Het snelst voor uw 8 pallets spuitbussen is Solace Air Cargo van Frankfurt (FRA) naar New York (JFK), EUR 1,308.21 all-in. Als het u schikt, kan het vrijdag vertrekken en rond 30/11 aankomen.
>
> Dit zijn gevaarlijke goederen, dus ik heb vóór het ophalen de Shipper's Declaration for Dangerous Goods en het veiligheidsinformatieblad (MSDS) nodig.
>
> Een kort antwoord is genoeg, dan boek ik het en wordt de plek daarna bevestigd.
>
> Met vriendelijke groet,
> Lena

**Booked**
> Hallo Sanne,
>
> Geregeld, geboekt bij Solace Air Cargo, FRA naar JFK, ref. BK-1A2B3C4D. Ik laat het weten zodra ze bevestigen.
>
> Groeten,
> Lena

**Airline confirmed**
> Hallo Sanne,
>
> Solace Air Cargo heeft BK-1A2B3C4D net bevestigd, alles staat klaar.
>
> Groeten,
> Lena

### pt

**Casual, door pickup, no packing word (weight)**
> Olá João,
>
> Para os seus 450 kg de peças de máquinas posso oferecer Solace Air Cargo de Frankfurt (FRA) para New York (JFK) por EUR 1,308.21 com tudo incluído, recolha em Bad Homburg incluída. Se lhe der jeito, podemos fazer a recolha na quinta-feira e deve chegar por volta de 30/11.
>
> Basta uma resposta curta, eu reservo e o espaço é confirmado depois.
>
> Cumprimentos,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Olá João Silva,
>
> Obrigada pelo pedido. O mais rápido para as suas 8 paletes de aerossóis é Solace Air Cargo de Frankfurt (FRA) para New York (JFK), EUR 1,308.21 com tudo incluído. Se lhe for conveniente, pode sair na sexta-feira e chegar por volta de 30/11.
>
> São mercadorias perigosas, por isso preciso da Shipper's Declaration for Dangerous Goods e da ficha de segurança (MSDS) antes da recolha.
>
> Basta uma resposta curta, eu reservo e o espaço é confirmado depois.
>
> Com os melhores cumprimentos,
> Lena

**Booked**
> Olá João,
>
> Feito, reservado com Solace Air Cargo, FRA para JFK, ref. BK-1A2B3C4D. Aviso assim que confirmarem.
>
> Cumprimentos,
> Lena

**Airline confirmed**
> Olá João,
>
> A Solace Air Cargo acabou de confirmar BK-1A2B3C4D, está tudo pronto.
>
> Cumprimentos,
> Lena

### tr

**Casual, door pickup, no packing word (weight)**
> Merhaba Deniz,
>
> 450 kg makine parçası için Solace Air Cargo ile Frankfurt (FRA) - New York (JFK) arası, Bad Homburg alımı ve her şey dahil toplamda EUR 1,308.21 tutuyor. Size de uyarsa perşembe günü alabiliriz, 30 Kasım civarı da varır.
>
> Kısa bir cevap yeterli, rezervasyonu yaparım, yer ise sonra onaylanır.
>
> Görüşmek üzere,
> Lena

**Formal, airport to airport, packing word, dangerous goods, fastest**
> Merhaba Deniz Yılmaz,
>
> Talebiniz için teşekkürler. 8 palet sprey kutusu için en hızlı seçenek Solace Air Cargo ile Frankfurt (FRA) - New York (JFK) arası, her şey dahil toplamda EUR 1,308.21 tutuyor. Uygun görürseniz cuma günü uçabilir, 30 Kasım civarı da varır.
>
> Bunlar tehlikeli madde sayıldığı için alımdan önce sizden Shipper's Declaration for Dangerous Goods ve güvenlik bilgi formunu (MSDS) rica edeceğim.
>
> Kısa bir cevap yeterli, rezervasyonu yaparım, yer ise sonra onaylanır.
>
> Saygılarımla,
> Lena

**Booked**
> Merhaba Deniz,
>
> Tamamdır, Solace Air Cargo ile FRA - JFK rezervasyonunu yaptım, referans BK-1A2B3C4D. Havayolu onaylayınca haber veririm.
>
> Görüşmek üzere,
> Lena

**Airline confirmed**
> Merhaba Deniz,
>
> Solace Air Cargo BK-1A2B3C4D rezervasyonunu onayladı, her şey hazır.
>
> Görüşmek üzere,
> Lena

### en, other situations

**One box, PO reference, pickup tomorrow**
> Hi Mike,
>
> re your PO-4711: for your box of spare parts I can do Solace Air Cargo from Frankfurt (FRA) to New York (JFK) for EUR 1,308.21 all in, pickup in Bad Homburg included. If that works for you, we can collect tomorrow and it should land around friday, about 3 days.
>
> just reply and I'll book it, space gets confirmed then.
>
> cheers,
> Lena

**No goods named, 3 crates**
> Hi Tom,
>
> for your 3 crates I can do Solace Air Cargo from Frankfurt (FRA) to New York (JFK) for EUR 1,308.21 all in, pickup in Bad Homburg included. If that works for you, we can collect thursday and they should land around 30 Nov, about 3 days.
>
> just reply and I'll book it, space gets confirmed then.
>
> cheers,
> Lena


## 7. Still AI-sounding (seen in live mails at 02:27, not fixed yet)

1. **Tracking answer repeats itself and echoes the system text** (`short_mail.tracking`).
   > BK-IG44QFLW (STR to MEL with Solace Air Cargo) is booked and confirmed by the airline, ready to go.
   > Latest from them: Booking BK-IG44QFLW confirmed by the airline. Transit's about 4 days.

   **Fix:** leave out the "Latest from them" line when the update only says the booking is confirmed (the status sentence already says so). Otherwise say it in our words, e.g. "The airline's latest: …". Also put the line breaks into one paragraph like the other mails: "BK-IG44QFLW is confirmed by Solace Air Cargo and ready to go, transit's about 4 days. I'll keep you posted."
2. **The full name in every mail of a formal thread** ("Hello Jonas Kessler," in the quote, the booking, the confirmation and the tracking answer). Nobody writes that four times.

   **Fix:** after the quote, if the customer's latest mail greets us by first name ("Hello Lena"), use their first name ("Hello Jonas,"). Otherwise use the title they wrote. Keep "Hello Jonas Kessler," only for the first mail.
3. **Formal greetings outside en/de:**
   - Spanish "Hola Lucía García," would be "Estimada Lucía García,".
   - Portuguese "Olá João Silva," would be "Caro João Silva,".
   - Turkish "Merhaba Deniz Yılmaz," would be "Sayın Deniz Yılmaz,".

   **Fix:** these are the `BETWEEN_HI` values in `short_mail.py` (formal only).

## 8. Files, tests, switches

- **Code:**
  - `agent/short_mail.py`: `BETWEEN`, `BETWEEN_SIGN`, `BETWEEN_HI`, `BETWEEN_HI_CASUAL`, `FORMAL_PLAN`, `CAPITAL_AFTER_HI`, `WEIGHT_GOODS`, `LOCAL_PACKING`, `PACKING`, `WHEN`, `between_quote`, `goods_words`, `_mail`
  - `agent/quote_style.py`: the switch
- **Tests:** `agent/test_between_style.py` (60 cases: every language, formal and casual, DG, one amount, no ISO dates, weight/packing words, formal sentence, capitals).
- **Full agent suite on Windows:** 2560 passed, 10 failed. **The same 10 fail on `main` without these changes:** fcntl/worker lock, tracking sweeps and the translation cache on Windows. On Linux, run `make check`.
- **Switches:**
  - `QUOTE_STYLE=between` is the default. `short`, `a` and `classic` are the older styles.
  - `MAIL_HUMAN` only affects the non-between styles.
- **Older design notes:** `docs/HUMAN_MAILS.md` on `ulas/human-mails` (the target mails the slot template came from).
