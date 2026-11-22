"""GATE_I18N (default on; off = every language but German gets the English sentence, as before).

Session 131: the quote gate's lower-deck sentence went out in English inside a Turkish mail. The gate's own sentences
(special cargo, batteries, oversize, late, over budget, insurance) in the other template languages (fr es it nl pt tr).
A sentence without a translation here stays English (never silently dropped: "over budget" and "not in time" must be
said, traps 5 and 6). No digits, no amounts, no references: the same facts as the English sentence.
"""
import os

ON = os.environ.get("GATE_I18N", "on").lower() != "off"

T = {
    # OVERSIZE
    "Some pieces are larger than lower-deck size, so they fly on a freighter's main deck: the airline confirms the space "
    "when we book.": {
        "fr": "Certains colis dépassent la taille des soutes inférieures et voleront donc sur le pont principal d'un "
              "cargo : la compagnie confirme la place à la réservation.",
        "es": "Algunos bultos superan el tamaño de la bodega inferior, por lo que vuelan en la cubierta principal de un "
              "carguero: la aerolínea confirma el espacio al reservar.",
        "it": "Alcuni colli superano le dimensioni della stiva inferiore, quindi volano sul ponte principale di un "
              "cargo: la compagnia conferma lo spazio alla prenotazione.",
        "nl": "Enkele colli zijn groter dan het onderdek toelaat en vliegen daarom op het hoofddek van een vrachtvliegtuig: "
              "de luchtvaartmaatschappij bevestigt de ruimte bij de boeking.",
        "pt": "Alguns volumes excedem o tamanho do porão inferior, por isso voam no convés principal de um cargueiro: "
              "a companhia confirma o espaço na reserva.",
        "tr": "Bazı koliler alt güverte ölçülerinden büyük olduğu için kargo uçağının ana güvertesinde uçacak: "
              "havayolu yeri rezervasyonda onaylıyor.",
    },
    # BATTERY_SENTENCE
    "As the goods usually contain lithium batteries, please confirm with your booking whether they ship with batteries "
    "(installed or packed with the equipment) and the battery type, so the airline accepts them under the right packing "
    "instruction.": {
        "fr": "Ces produits contenant souvent des batteries lithium, merci de confirmer avec la réservation s'ils voyagent "
              "avec des batteries (intégrées ou emballées avec l'appareil) et le type de batterie, afin que la compagnie "
              "les accepte sous la bonne instruction d'emballage.",
        "es": "Como estos productos suelen llevar baterías de litio, confírmenos con la reserva si viajan con baterías "
              "(instaladas o embaladas con el equipo) y el tipo de batería, para que la aerolínea los acepte con la "
              "instrucción de embalaje correcta.",
        "it": "Poiché questi prodotti contengono spesso batterie al litio, confermateci con la prenotazione se viaggiano "
              "con batterie (installate o imballate con l'apparecchio) e il tipo di batteria, così la compagnia li accetta "
              "con la giusta istruzione di imballaggio.",
        "nl": "Omdat zulke goederen meestal lithiumbatterijen bevatten, bevestig bij de boeking of ze met batterijen reizen "
              "(ingebouwd of bijgepakt) en welk batterijtype, zodat de luchtvaartmaatschappij ze onder de juiste "
              "verpakkingsinstructie aanneemt.",
        "pt": "Como estes produtos costumam ter baterias de lítio, confirme com a reserva se viajam com baterias "
              "(instaladas ou embaladas com o equipamento) e o tipo de bateria, para que a companhia os aceite com a "
              "instrução de embalagem correta.",
        "tr": "Bu ürünlerde genellikle lityum pil bulunduğundan, rezervasyonla birlikte pilli mi gönderildiklerini "
              "(takılı ya da cihazla birlikte paketli) ve pil tipini teyit eder misiniz? Böylece havayolu doğru paketleme "
              "talimatıyla kabul eder.",
    },
    # SPECIAL: temperature
    "As the goods need a controlled temperature, please confirm the required range and whether a data logger travels "
    "with the shipment: the airline confirms temperature-controlled handling when we book.": {
        "fr": "La marchandise devant voyager à température dirigée, merci de confirmer la plage requise et si un "
              "enregistreur de données l'accompagne : la compagnie confirme la manutention sous température à la "
              "réservation.",
        "es": "Como la mercancía necesita temperatura controlada, confírmenos el rango requerido y si viaja un registrador "
              "de datos con el envío: la aerolínea confirma el manejo a temperatura controlada al reservar.",
        "it": "Poiché la merce richiede una temperatura controllata, confermateci l'intervallo necessario e se viaggia un "
              "data logger con la spedizione: la compagnia conferma la gestione a temperatura controllata alla "
              "prenotazione.",
        "nl": "Omdat de goederen een gecontroleerde temperatuur nodig hebben, bevestig het vereiste bereik en of er een "
              "datalogger meereist: de luchtvaartmaatschappij bevestigt de temperatuurgecontroleerde afhandeling bij de "
              "boeking.",
        "pt": "Como a mercadoria precisa de temperatura controlada, confirme a faixa necessária e se um registrador de "
              "dados viaja com o envio: a companhia confirma o manuseio com temperatura controlada na reserva.",
        "tr": "Ürünün kontrollü sıcaklıkta taşınması gerektiğinden, gereken sıcaklık aralığını ve gönderiyle bir veri "
              "kaydedici gidip gitmediğini teyit eder misiniz? Havayolu sıcaklık kontrollü elleçlemeyi rezervasyonda "
              "onaylıyor.",
    },
    # SPECIAL: perishable
    "We book the shipment as perishable cargo with priority handling at both airports.": {
        "fr": "Nous réservons l'envoi comme marchandise périssable avec traitement prioritaire dans les deux aéroports.",
        "es": "Reservamos el envío como carga perecedera con manejo prioritario en ambos aeropuertos.",
        "it": "Prenotiamo la spedizione come merce deperibile con gestione prioritaria in entrambi gli aeroporti.",
        "nl": "We boeken de zending als bederfelijke lading met voorrang bij de afhandeling op beide luchthavens.",
        "pt": "Reservamos o envio como carga perecível com manuseio prioritário nos dois aeroportos.",
        "tr": "Gönderiyi her iki havalimanında öncelikli elleçlemeyle bozulabilir kargo olarak rezerve ediyoruz.",
    },
    # SPECIAL: valuables
    "As valuable cargo the shipment gets secure handling and storage; please let us know the declared value.": {
        "fr": "En tant que fret de valeur, l'envoi bénéficie d'une manutention et d'un stockage sécurisés ; merci de nous "
              "indiquer la valeur déclarée.",
        "es": "Como carga valiosa, el envío recibe manejo y almacenaje seguros; indíquenos el valor declarado.",
        "it": "Come merce di valore la spedizione ha gestione e deposito sicuri; indicateci il valore dichiarato.",
        "nl": "Als waardevolle lading krijgt de zending beveiligde afhandeling en opslag; laat ons de aangegeven waarde "
              "weten.",
        "pt": "Como carga valiosa, o envio tem manuseio e armazenagem seguros; informe-nos o valor declarado.",
        "tr": "Değerli kargo olarak gönderi güvenli elleçleme ve depolamadan geçiyor; lütfen beyan edilen değeri "
              "bildirin.",
    },
    # SPECIAL: non_stackable
    "We have noted that the pieces must not be stacked and book the space accordingly.": {
        "fr": "Nous avons noté que les colis ne doivent pas être gerbés et réservons la place en conséquence.",
        "es": "Hemos anotado que los bultos no se pueden apilar y reservamos el espacio en consecuencia.",
        "it": "Abbiamo annotato che i colli non sono sovrapponibili e prenotiamo lo spazio di conseguenza.",
        "nl": "We hebben genoteerd dat de colli niet gestapeld mogen worden en boeken de ruimte daarop.",
        "pt": "Anotámos que os volumes não podem ser empilhados e reservamos o espaço em conformidade.",
        "tr": "Kolilerin üst üste konulamayacağını not ettik ve yeri buna göre rezerve ediyoruz.",
    },
    # LATE
    "Please note that none of the available flights gets there in time for what you asked: this is the best we can "
    "offer, so let me know if it still works for you.": {
        "fr": "Veuillez noter qu'aucun des vols disponibles n'arrive à temps pour la date demandée : c'est la meilleure "
              "offre possible, dites-moi si elle vous convient quand même.",
        "es": "Tenga en cuenta que ninguno de los vuelos disponibles llega a tiempo para lo que pidió: es lo mejor que "
              "podemos ofrecer, dígame si aun así le sirve.",
        "it": "Tenga presente che nessuno dei voli disponibili arriva in tempo per la data richiesta: è la migliore "
              "offerta possibile, mi dica se va bene lo stesso.",
        "nl": "Let op: geen van de beschikbare vluchten is op tijd voor de gevraagde datum. Dit is het beste dat we kunnen "
              "bieden, laat me weten of het toch past.",
        "pt": "Note que nenhum dos voos disponíveis chega a tempo para o que pediu: é o melhor que podemos oferecer, "
              "diga-me se ainda lhe serve.",
        "tr": "Lütfen dikkat: Mevcut uçuşların hiçbiri istediğiniz tarihe yetişmiyor. Sunabileceğimiz en iyi seçenek bu, "
              "yine de uygun olup olmadığını bana bildirin.",
    },
    # LATE_BETWEEN
    "Heads-up: none of the flights gets there in time for the date you asked, this is the best I can offer, so let me "
    "know if it still works for you.": {
        "fr": "Petite remarque : aucun vol n'arrive à temps pour la date demandée, c'est le mieux que je puisse proposer, "
              "dites-moi si ça vous va quand même.",
        "es": "Un aviso: ningún vuelo llega a tiempo para la fecha que pidió, es lo mejor que puedo ofrecer, dígame si aun "
              "así le sirve.",
        "it": "Una nota: nessun volo arriva in tempo per la data richiesta, è il meglio che posso offrire, mi dica se va "
              "bene lo stesso.",
        "nl": "Even een kanttekening: geen enkele vlucht is op tijd voor de gevraagde datum, dit is het beste wat ik kan "
              "bieden, laat me weten of het toch past.",
        "pt": "Um aviso: nenhum voo chega a tempo para a data pedida, é o melhor que posso oferecer, diga-me se ainda "
              "lhe serve.",
        "tr": "Kısa bir not: Uçuşların hiçbiri istediğiniz tarihe yetişmiyor, sunabileceğim en iyi seçenek bu, yine de "
              "uygun olup olmadığını bana bildirin.",
    },
    # OVER_BUDGET
    "Please note that this is above the budget you mentioned: it is the best all-in price on this lane for your dates, "
    "so let me know if we should go ahead.": {
        "fr": "Veuillez noter que ce prix dépasse le budget indiqué : c'est le meilleur prix tout compris sur cette ligne "
              "pour vos dates, dites-moi si nous lançons la réservation.",
        "es": "Tenga en cuenta que está por encima del presupuesto que mencionó: es el mejor precio todo incluido en esta "
              "ruta para sus fechas, dígame si seguimos adelante.",
        "it": "Tenga presente che è sopra il budget indicato: è il miglior prezzo tutto incluso su questa tratta per le "
              "sue date, mi dica se procediamo.",
        "nl": "Let op: dit ligt boven het genoemde budget. Het is de beste all-in prijs op deze route voor uw data, laat me "
              "weten of we doorgaan.",
        "pt": "Note que está acima do orçamento que indicou: é o melhor preço com tudo incluído nesta rota para as suas "
              "datas, diga-me se avançamos.",
        "tr": "Lütfen dikkat: Bu fiyat belirttiğiniz bütçenin üzerinde. Tarihleriniz için bu hatta alabileceğimiz en iyi "
              "her şey dahil fiyat bu, devam edelim mi bana bildirin.",
    },
    # OVER_BUDGET_BETWEEN
    "I know that's above the budget you mentioned, but it's the best all-in price I can get on this lane for your "
    "dates.": {
        "fr": "Je sais que c'est au-dessus du budget indiqué, mais c'est le meilleur prix tout compris que je trouve sur "
              "cette ligne pour vos dates.",
        "es": "Sé que está por encima del presupuesto que mencionó, pero es el mejor precio todo incluido que consigo en "
              "esta ruta para sus fechas.",
        "it": "So che è sopra il budget indicato, ma è il miglior prezzo tutto incluso che trovo su questa tratta per le "
              "sue date.",
        "nl": "Ik weet dat het boven het genoemde budget ligt, maar het is de beste all-in prijs die ik op deze route voor "
              "uw data krijg.",
        "pt": "Sei que está acima do orçamento que indicou, mas é o melhor preço com tudo incluído que consigo nesta rota "
              "para as suas datas.",
        "tr": "Belirttiğiniz bütçenin üzerinde olduğunu biliyorum ama tarihleriniz için bu hatta alabildiğim en iyi her "
              "şey dahil fiyat bu.",
    },
    # INSURED
    "The all-in price includes the cargo insurance premium on the terms you gave.": {
        "fr": "Le prix tout compris inclut la prime d'assurance marchandises aux conditions indiquées.",
        "es": "El precio todo incluido contiene la prima del seguro de carga en las condiciones que indicó.",
        "it": "Il prezzo tutto incluso comprende il premio dell'assicurazione merci alle condizioni indicate.",
        "nl": "De all-in prijs omvat de premie van de transportverzekering volgens uw voorwaarden.",
        "pt": "O preço com tudo incluído contém o prémio do seguro de carga nas condições que indicou.",
        "tr": "Her şey dahil fiyata, verdiğiniz koşullarla kargo sigortası primi de dahil.",
    },
}


def say(en: str, de: str, lang: str) -> str:
    """The gate sentence in the mail's language: German as before, the other template languages from T, else English."""
    if lang == "de":
        return de
    if ON and lang in ("fr", "es", "it", "nl", "pt", "tr"):
        return T.get(en, {}).get(lang, en)
    return en
