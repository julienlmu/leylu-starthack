"""The quote gate's and shapes.py's sentences in the other template languages (fr, es, it, nl, pt, tr).

gate.py and shapes.py write each sentence as an (English, German) pair; every other language got the English one in the
middle of a French or Turkish mail. This table gives the same sentence in the customer's language, written the way the
between mails are (connectors instead of comma chains, no "Please note", no digits: one amount per mail).
Keys are the English originals, registered by gate.py / shapes.py, so a reworded English sentence never breaks a lookup
silently: an unknown sentence simply stays English.
"""

LANGS = ("fr", "es", "it", "nl", "pt", "tr")
AND = {"en": "and", "de": "und", "fr": "et", "es": "y", "it": "e", "nl": "en", "pt": "e", "tr": "ve"}

T = {
    "temperature": {
        "fr": "La marchandise doit voyager à température contrôlée et j'ai donc besoin de la plage requise et de savoir "
              "si un enregistreur de données l'accompagne. La compagnie confirme ce transport à la réservation.",
        "es": "La mercancía necesita temperatura controlada así que necesito saber el rango requerido y si viaja con un "
              "registrador de datos. La aerolínea confirma ese manejo al hacer la reserva.",
        "it": "La merce deve viaggiare a temperatura controllata e quindi mi serve l'intervallo richiesto e sapere se "
              "viaggia con un data logger. La compagnia conferma questo trasporto al momento della prenotazione.",
        "nl": "De goederen moeten op een gecontroleerde temperatuur blijven en daarom hoor ik graag het vereiste bereik "
              "en of er een datalogger meereist. De luchtvaartmaatschappij bevestigt dat bij het boeken.",
        "pt": "A mercadoria precisa de temperatura controlada e por isso preciso da faixa exigida e de saber se segue com "
              "um registador de dados. A companhia aérea confirma esse manuseamento na reserva.",
        "tr": "Yükün kontrollü sıcaklıkta taşınması gerektiği için gereken sıcaklık aralığını ve yanında veri kaydedici "
              "olup olmadığını öğrenmem lazım. Havayolu bunu rezervasyonda onaylıyor."},
    "perishable": {
        "fr": "Je réserve l'envoi comme marchandise périssable avec un traitement prioritaire dans les deux aéroports.",
        "es": "Reservo el envío como carga perecedera con prioridad de manejo en los dos aeropuertos.",
        "it": "Prenoto la spedizione come merce deperibile con gestione prioritaria in entrambi gli aeroporti.",
        "nl": "Ik boek de zending als bederfelijke lading met voorrang op beide luchthavens.",
        "pt": "Reservo o envio como carga perecível com prioridade de manuseamento nos dois aeroportos.",
        "tr": "Gönderiyi bozulabilir yük olarak her iki havalimanında öncelikli işlemle rezerve ediyorum."},
    "valuables": {
        "fr": "L'envoi passe en fret de valeur avec une manutention et un stockage sécurisés et j'ai juste besoin de la "
              "valeur déclarée.",
        "es": "El envío va como carga valiosa con manejo y almacenaje seguros y solo necesito el valor declarado.",
        "it": "La spedizione viaggia come merce di valore con gestione e deposito sicuri e mi serve solo il valore "
              "dichiarato.",
        "nl": "De zending gaat als waardevolle lading met beveiligde behandeling en opslag en ik heb alleen nog de "
              "opgegeven waarde nodig.",
        "pt": "O envio segue como carga valiosa com manuseamento e armazenagem seguros e só preciso do valor declarado.",
        "tr": "Gönderi değerli yük olarak güvenli şekilde taşınıp depolanıyor ve sadece beyan edilen değere ihtiyacım var."},
    "non_stackable": {
        "fr": "J'ai bien noté que les colis ne doivent pas être gerbés et je réserve la place en conséquence.",
        "es": "He anotado que los bultos no se pueden apilar y reservo el espacio en consecuencia.",
        "it": "Ho preso nota che i colli non vanno sovrapposti e prenoto lo spazio di conseguenza.",
        "nl": "Ik heb genoteerd dat de colli niet gestapeld mogen worden en boek de ruimte daarop.",
        "pt": "Tomei nota de que os volumes não podem ser empilhados e reservo o espaço de acordo.",
        "tr": "Parçaların üst üste konamayacağını not ettim ve yeri buna göre ayırıyorum."},
    "battery": {
        "fr": "Ce type de marchandise contient souvent des batteries au lithium et j'ai donc besoin de savoir avec votre "
              "accord si elles voyagent avec des batteries (installées ou emballées avec l'équipement) et de quel type "
              "pour que la compagnie les accepte sous la bonne instruction d'emballage.",
        "es": "Este tipo de mercancía suele llevar baterías de litio y por eso necesito saber con su confirmación si van "
              "con baterías (instaladas o embaladas con el equipo) y de qué tipo para que la aerolínea las acepte con la "
              "instrucción de embalaje correcta.",
        "it": "Questo tipo di merce di solito contiene batterie al litio e quindi mi serve sapere con la sua conferma se "
              "viaggiano con batterie (installate o imballate con l'apparecchio) e di che tipo perché la compagnia le "
              "accetti con l'istruzione di imballaggio giusta.",
        "nl": "Dit soort goederen bevat meestal lithiumbatterijen en daarom hoor ik bij uw bevestiging graag of ze met "
              "batterijen reizen (ingebouwd of meeverpakt) en welk type zodat de luchtvaartmaatschappij ze onder de "
              "juiste verpakkingsinstructie accepteert.",
        "pt": "Este tipo de mercadoria costuma ter baterias de lítio e por isso preciso de saber com a sua confirmação se "
              "seguem com baterias (instaladas ou embaladas com o equipamento) e de que tipo para que a companhia aérea "
              "as aceite com a instrução de embalagem certa.",
        "tr": "Bu tür ürünlerde genelde lityum pil bulunuyor ve bu yüzden onayınızla birlikte pil olup olmadığını (cihazın "
              "içinde ya da yanında paketli) ve pil tipini bilmem gerekiyor ki havayolu doğru paketleme talimatıyla "
              "kabul etsin."},
    "oversize": {
        "fr": "Certains colis dépassent la taille de la soute et voyagent donc sur le pont principal d'un avion cargo. La "
              "compagnie confirme la place à la réservation.",
        "es": "Algunos bultos superan el tamaño de la bodega inferior y por eso van en la cubierta principal de un "
              "carguero. La aerolínea confirma el espacio al reservar.",
        "it": "Alcuni colli superano la misura della stiva e quindi volano sul ponte principale di un cargo. La compagnia "
              "conferma lo spazio alla prenotazione.",
        "nl": "Een paar colli zijn groter dan het onderdek toelaat en vliegen dus op het hoofddek van een vrachtvliegtuig. "
              "De luchtvaartmaatschappij bevestigt de ruimte bij het boeken.",
        "pt": "Alguns volumes são maiores do que o porão permite e por isso voam no convés principal de um cargueiro. A "
              "companhia aérea confirma o espaço na reserva.",
        "tr": "Bazı parçalar alt güverteye sığmadığı için kargo uçağının ana güvertesinde uçuyor. Havayolu yeri "
              "rezervasyonda onaylıyor."},
    "insured": {
        "fr": "L'assurance est aussi comprise dans le prix aux conditions que vous avez indiquées.",
        "es": "El seguro también está incluido en el precio con las condiciones que me indicó.",
        "it": "Anche l'assicurazione è inclusa nel prezzo alle condizioni che mi ha indicato.",
        "nl": "De verzekering zit ook in de prijs volgens uw voorwaarden.",
        "pt": "O seguro também está incluído no preço nas condições que me indicou.",
        "tr": "Sigorta da belirttiğiniz şartlarla fiyata dahil."},
    "insurance_ask": {
        "fr": "Merci pour votre demande ! Pour inclure l'assurance dans le prix tout compris il me faut la valeur de la "
              "marchandise, la couverture (par exemple une part de la valeur facturée) et le taux de prime ou la prime "
              "minimale de votre assureur. Je vous envoie le prix complet dès que je les ai.",
        "es": "¡Gracias por su solicitud! Para incluir el seguro en el precio todo incluido necesito el valor de la "
              "mercancía, la cobertura (por ejemplo una parte del valor de factura) y la tasa de prima o la prima mínima "
              "de su aseguradora. Le envío el precio completo en cuanto los tenga.",
        "it": "grazie per la richiesta! Per includere l'assicurazione nel prezzo all-in mi servono il valore della merce, "
              "la copertura (per esempio una quota del valore fattura) e il tasso di premio o il premio minimo del suo "
              "assicuratore. Le mando il prezzo completo appena li ho.",
        "nl": "Bedankt voor uw aanvraag! Om de verzekering in de all-in prijs op te nemen heb ik de goederenwaarde, de "
              "dekking (bijvoorbeeld een deel van de factuurwaarde) en het premiepercentage of de minimumpremie van uw "
              "verzekeraar nodig. Ik stuur u de volledige prijs zodra ik die heb.",
        "pt": "Obrigada pelo seu pedido! Para incluir o seguro no preço all-in preciso do valor da mercadoria, da "
              "cobertura (por exemplo uma parte do valor da fatura) e da taxa de prémio ou do prémio mínimo da sua "
              "seguradora. Envio-lhe o preço completo assim que os tiver.",
        "tr": "Talebiniz için teşekkürler! Sigortayı her şey dahil fiyata eklemem için mal bedeli, teminat (örneğin fatura "
              "bedelinin bir oranı) ve prim oranı ya da sigortacınızın asgari primi lazım. Bunları alır almaz tam fiyatı "
              "gönderiyorum."},
    "late": {
        "fr": "Aucun des vols n'arrive malheureusement à temps pour la date demandée et c'est le mieux que je puisse "
              "proposer, dites-moi si ça vous convient quand même.",
        "es": "Ninguno de los vuelos llega a tiempo para la fecha que pidió y esto es lo mejor que puedo ofrecer, así que "
              "dígame si le sirve igualmente.",
        "it": "Purtroppo nessuno dei voli arriva in tempo per la data richiesta e questo è il meglio che posso offrire, mi "
              "dica se va bene lo stesso.",
        "nl": "Helaas is geen van de vluchten op tijd voor de gevraagde datum en dit is het beste wat ik kan aanbieden, "
              "dus laat me weten of het toch past.",
        "pt": "Infelizmente nenhum dos voos chega a tempo para a data pedida e isto é o melhor que posso oferecer, por "
              "isso diga-me se serve na mesma.",
        "tr": "Maalesef uçuşların hiçbiri istediğiniz tarihe yetişmiyor ve sunabileceğim en iyisi bu, yine de uyarsa haber "
              "verin."},
    "over_budget": {
        "fr": "Je sais que c'est au-dessus du budget indiqué mais c'est le meilleur prix tout compris que je trouve sur "
              "cette ligne pour vos dates.",
        "es": "Sé que está por encima del presupuesto que mencionó pero es el mejor precio todo incluido que consigo en "
              "esta ruta para sus fechas.",
        "it": "So che è sopra il budget indicato ma è il miglior prezzo all-in che trovo su questa tratta per le sue date.",
        "nl": "Ik weet dat dit boven het genoemde budget ligt maar het is de beste all-in prijs die ik op deze route voor "
              "uw data kan krijgen.",
        "pt": "Sei que está acima do orçamento que indicou mas é o melhor preço all-in que consigo nesta rota para as "
              "suas datas.",
        "tr": "Belirttiğiniz bütçenin üstünde olduğunu biliyorum ama bu tarihler için bu hatta bulabildiğim en iyi her "
              "şey dahil fiyat bu."},
    "required_carrier": {
        "fr": "Merci pour votre demande ! {names} n'a pas de tarif de {o} à {d} pour vos dates. Je vous propose une autre "
              "compagnie ou vous préférez rester avec {names} ?",
        "es": "¡Gracias por su solicitud! {names} no tiene tarifa de {o} a {d} para sus fechas. ¿Le cotizo otra aerolínea "
              "o prefiere quedarse con {names}?",
        "it": "grazie per la richiesta! {names} non ha una tariffa da {o} a {d} per le sue date. Le propongo un'altra "
              "compagnia o preferisce restare con {names}?",
        "nl": "Bedankt voor uw aanvraag! {names} heeft geen tarief van {o} naar {d} voor uw data. Zal ik een andere "
              "maatschappij aanbieden of blijft u liever bij {names}?",
        "pt": "Obrigada pelo seu pedido! A {names} não tem tarifa de {o} para {d} nas suas datas. Quer que cote outra "
              "companhia ou prefere ficar com a {names}?",
        "tr": "Talebiniz için teşekkürler! {names} tarihleriniz için {o} - {d} arasında fiyat vermiyor. Başka bir havayolu "
              "mu teklif edeyim yoksa {names} ile mi devam etmek istersiniz?"},
    "excluded_carrier": {
        "fr": "Merci pour votre demande ! De {o} à {d} seules les compagnies que vous avez exclues ont un tarif pour vos "
              "dates. Je vous en propose une quand même ou je cherche un autre itinéraire ?",
        "es": "¡Gracias por su solicitud! De {o} a {d} solo tienen tarifa para sus fechas las aerolíneas que excluyó. ¿Le "
              "cotizo una de ellas de todos modos o busco otra ruta?",
        "it": "grazie per la richiesta! Da {o} a {d} hanno una tariffa per le sue date solo le compagnie che ha escluso. "
              "Gliene propongo comunque una o cerco un altro percorso?",
        "nl": "Bedankt voor uw aanvraag! Van {o} naar {d} hebben alleen de maatschappijen die u uitsloot een tarief voor "
              "uw data. Zal ik er toch een aanbieden of zoek ik een andere route?",
        "pt": "Obrigada pelo seu pedido! De {o} para {d} só as companhias que excluiu têm tarifa nas suas datas. Quer que "
              "cote uma delas mesmo assim ou procuro outra rota?",
        "tr": "Talebiniz için teşekkürler! {o} - {d} arasında tarihleriniz için sadece kullanmamamızı istediğiniz "
              "havayollarının fiyatı var. Yine de birini mi teklif edeyim yoksa başka bir rota mı arayayım?"},
    "dg_refused": {
        "fr": "Merci pour votre demande ! Les compagnies qui ont un tarif de {o} à {d} n'acceptent pas ces marchandises "
              "dangereuses. Je vous cherche un autre itinéraire ?",
        "es": "¡Gracias por su solicitud! Las aerolíneas con tarifa de {o} a {d} no aceptan estas mercancías peligrosas. "
              "¿Le busco otra ruta?",
        "it": "grazie per la richiesta! Le compagnie con una tariffa da {o} a {d} non accettano queste merci pericolose. "
              "Le cerco un altro percorso?",
        "nl": "Bedankt voor uw aanvraag! De maatschappijen met een tarief van {o} naar {d} nemen deze gevaarlijke goederen "
              "niet mee. Zal ik een andere route voor u zoeken?",
        "pt": "Obrigada pelo seu pedido! As companhias com tarifa de {o} para {d} não aceitam estas mercadorias perigosas. "
              "Quer que procure outra rota?",
        "tr": "Talebiniz için teşekkürler! {o} - {d} arasında fiyatı olan havayolları bu tehlikeli maddeleri kabul etmiyor. "
              "Sizin için başka bir rota arayayım mı?"},
    "door_sentence": {
        "fr": "Le prix tout compris couvre le fret aérien jusqu'à l'aéroport de {dest} et la livraison chez le "
              "destinataire, le dédouanement et les droits à l'arrivée n'en font pas partie, mais je peux volontiers les "
              "organiser à part.",
        "es": "El precio todo incluido cubre el flete aéreo hasta el aeropuerto de {dest} y la entrega al destinatario, "
              "el despacho de importación y los aranceles en destino no están incluidos, aunque con gusto los organizo "
              "aparte.",
        "it": "Il prezzo all-in copre il trasporto aereo fino all'aeroporto di {dest} e la consegna al destinatario, lo "
              "sdoganamento e i dazi a destinazione non sono inclusi, ma posso organizzarli volentieri a parte.",
        "nl": "De all-in prijs geldt voor de luchtvracht tot de luchthaven van {dest} en de levering bij de ontvanger, de "
              "invoerinklaring en de heffingen op de bestemming zitten er niet in, maar die regel ik graag apart.",
        "pt": "O preço all-in cobre o frete aéreo até ao aeroporto de {dest} e a entrega ao destinatário, o "
              "desalfandegamento e os direitos no destino não estão incluídos, mas posso tratar disso à parte.",
        "tr": "Her şey dahil fiyat {dest} havalimanına kadar olan hava taşımasını kapsıyor ve alıcıya teslim, ithalat "
              "gümrüklemesi ve vergiler dahil değil ama bunları ayrıca memnuniyetle ayarlarım."},
    "door_ask": {
        "fr": "Merci pour votre demande ! Notre prix couvre le fret aérien jusqu'à l'aéroport de {dest} et j'organise la "
              "livraison chez le destinataire, le dédouanement et les droits avec un partenaire local. Je les fais "
              "chiffrer aussi ou un prix d'aéroport à aéroport vous convient ?",
        "es": "¡Gracias por su solicitud! Nuestro precio cubre el flete aéreo hasta el aeropuerto de {dest} y la entrega "
              "al destinatario, el despacho y los aranceles los organizo con un socio local. ¿Se los cotizo también o le "
              "sirve un precio de aeropuerto a aeropuerto?",
        "it": "grazie per la richiesta! Il nostro prezzo copre il trasporto aereo fino all'aeroporto di {dest} e la "
              "consegna al destinatario, lo sdoganamento e i dazi li organizzo con un partner locale. Li faccio quotare "
              "anche o le va bene un prezzo da aeroporto ad aeroporto?",
        "nl": "Bedankt voor uw aanvraag! Onze prijs geldt voor de luchtvracht tot de luchthaven van {dest} en de levering "
              "bij de ontvanger, de inklaring en de heffingen regel ik met een lokale partner. Zal ik die ook laten "
              "offreren of is een prijs van luchthaven tot luchthaven goed?",
        "pt": "Obrigada pelo seu pedido! O nosso preço cobre o frete aéreo até ao aeroporto de {dest} e a entrega ao "
              "destinatário, o desalfandegamento e os direitos trato com um parceiro local. Quer que cote isso também ou "
              "um preço de aeroporto a aeroporto serve?",
        "tr": "Talebiniz için teşekkürler! Fiyatımız {dest} havalimanına kadar olan hava taşımasını kapsıyor ve alıcıya "
              "teslim, gümrükleme ve vergileri yerel bir partnerle ayarlıyorum. Bunlar için de teklif alayım mı yoksa "
              "havalimanından havalimanına fiyat yeterli mi?"},
    "faster": {
        "fr": "Si la rapidité compte davantage {carrier} arrive plus tôt et je vous propose volontiers cette option à la "
              "place.",
        "es": "Si le importa más la rapidez {carrier} llega antes y con gusto le cotizo esa opción.",
        "it": "Se conta di più la velocità {carrier} arriva prima e le propongo volentieri quell'opzione.",
        "nl": "Is snelheid belangrijker dan komt {carrier} eerder aan en bied ik u graag die optie aan.",
        "pt": "Se a rapidez for mais importante a {carrier} chega mais cedo e posso cotar essa opção em vez desta.",
        "tr": "Hız daha önemliyse {carrier} daha erken ulaştırıyor ve isterseniz o seçeneği teklif ederim."},
    "cheaper": {
        "fr": "Si le prix compte davantage {carrier} est l'option la plus économique et je vous la propose volontiers à la "
              "place.",
        "es": "Si le importa más el precio {carrier} es la opción más económica y con gusto se la cotizo.",
        "it": "Se conta di più il prezzo {carrier} è l'opzione più economica e gliela propongo volentieri.",
        "nl": "Is de prijs belangrijker dan is {carrier} de voordeligere optie en bied ik u die graag aan.",
        "pt": "Se o preço for mais importante a {carrier} é a opção mais económica e posso cotá-la em vez desta.",
        "tr": "Fiyat daha önemliyse {carrier} daha ekonomik seçenek ve isterseniz onu teklif ederim."},
    "lot_one_named": {
        "fr": "Cette offre est pour l'envoi vers {dest} et pour l'envoi vers {others} je vous envoie une offre séparée ou "
              "vous me confirmez simplement les détails.",
        "es": "Esta oferta es para el envío a {dest} y para el envío a {others} le mando una oferta aparte o me confirma "
              "los detalles.",
        "it": "Questa offerta è per la spedizione verso {dest} e per quella verso {others} le mando un'offerta a parte "
              "oppure mi conferma i dettagli.",
        "nl": "Deze offerte is voor de zending naar {dest} en voor de zending naar {others} stuur ik u een aparte offerte "
              "of u bevestigt gewoon de details.",
        "pt": "Esta proposta é para o envio para {dest} e para o envio para {others} mando-lhe uma proposta à parte ou "
              "confirma-me só os detalhes.",
        "tr": "Bu teklif {dest} gönderisi için ve {others} gönderisi için ayrı bir teklif gönderiyorum ya da detayları "
              "kısaca onaylayabilirsiniz."},
    "lot_several_named": {
        "fr": "Cette offre est pour l'envoi vers {dest} et pour les envois vers {others} je vous envoie des offres "
              "séparées ou vous me confirmez simplement les détails.",
        "es": "Esta oferta es para el envío a {dest} y para los envíos a {others} le mando ofertas aparte o me confirma "
              "los detalles.",
        "it": "Questa offerta è per la spedizione verso {dest} e per quelle verso {others} le mando offerte a parte oppure "
              "mi conferma i dettagli.",
        "nl": "Deze offerte is voor de zending naar {dest} en voor de zendingen naar {others} stuur ik u aparte offertes "
              "of u bevestigt gewoon de details.",
        "pt": "Esta proposta é para o envio para {dest} e para os envios para {others} mando-lhe propostas à parte ou "
              "confirma-me só os detalhes.",
        "tr": "Bu teklif {dest} gönderisi için ve {others} gönderileri için ayrı teklifler gönderiyorum ya da detayları "
              "kısaca onaylayabilirsiniz."},
    "lot_one": {
        "fr": "Cette offre est pour le premier de vos envois et pour l'autre je vous envoie une offre séparée ou vous me "
              "confirmez simplement les détails.",
        "es": "Esta oferta es para el primero de sus envíos y para el otro le mando una oferta aparte o me confirma los "
              "detalles.",
        "it": "Questa offerta è per la prima delle sue spedizioni e per l'altra le mando un'offerta a parte oppure mi "
              "conferma i dettagli.",
        "nl": "Deze offerte is voor de eerste van uw zendingen en voor de andere stuur ik u een aparte offerte of u "
              "bevestigt gewoon de details.",
        "pt": "Esta proposta é para o primeiro dos seus envios e para o outro mando-lhe uma proposta à parte ou "
              "confirma-me só os detalhes.",
        "tr": "Bu teklif gönderilerinizin ilki için ve diğeri için ayrı bir teklif gönderiyorum ya da detayları kısaca "
              "onaylayabilirsiniz."},
    "lot_several": {
        "fr": "Cette offre est pour le premier de vos envois et pour les autres je vous envoie des offres séparées ou vous "
              "me confirmez simplement les détails.",
        "es": "Esta oferta es para el primero de sus envíos y para los demás le mando ofertas aparte o me confirma los "
              "detalles.",
        "it": "Questa offerta è per la prima delle sue spedizioni e per le altre le mando offerte a parte oppure mi "
              "conferma i dettagli.",
        "nl": "Deze offerte is voor de eerste van uw zendingen en voor de andere zendingen stuur ik u aparte offertes of "
              "u bevestigt gewoon de details.",
        "pt": "Esta proposta é para o primeiro dos seus envios e para os outros mando-lhe propostas à parte ou confirma-me "
              "só os detalhes.",
        "tr": "Bu teklif gönderilerinizin ilki için ve diğerleri için ayrı teklifler gönderiyorum ya da detayları kısaca "
              "onaylayabilirsiniz."},
}

_BY_EN: dict[str, str] = {}


def register(pairs: dict[str, tuple]) -> None:
    """{key: (english, german)}: remembers which English sentence is which key."""
    for key, pair in pairs.items():
        _BY_EN[pair[0]] = key


def say(en: str, lang: str) -> str:
    """The English sentence in `lang` when we have it, else the English one (en, and languages without a table)."""
    key = _BY_EN.get(en)
    return T.get(key, {}).get(lang, en) if key and lang in LANGS else en


def pick(pair: tuple, lang: str) -> str:
    """An (english, german) pair in the customer's language."""
    return pair[1] if lang == "de" else say(pair[0], lang)
