// Invented sample data in the PLAN.md §7 shapes. Used when the backend is not reachable.
// Customers, rates and AWB numbers are fictional: one night shift, an RFQ every 6 minutes.
import type { Event, PriceOption, Session } from "./types";

const t = (hhmmss: string) => `2026-11-21T${hhmmss}+01:00`;
const eur = (n: number) => `EUR ${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Builds a price option whose total is the sum of its breakdown, like the pricing module does.
function rate(
  source: PriceOption["source"],
  carrier: string,
  rate_id: string | null,
  cw: number,
  perKg: number,
  transit_days: number,
  extra: { pickup?: { zone: string; fee: number }; fuel?: number } = {},
): PriceOption {
  const fuel = extra.fuel ?? 0.62;
  const breakdown = [
    { label: `Freight ${cw} kg × ${perKg.toFixed(2)}`, amount: round(cw * perKg) },
    { label: `Fuel surcharge ${cw} kg × ${fuel.toFixed(2)}`, amount: round(cw * fuel) },
    { label: `Security ${cw} kg × 0.15`, amount: round(cw * 0.15) },
    { label: "AWB fee", amount: 25 },
    ...(extra.pickup ? [{ label: `Pickup zone ${extra.pickup.zone}`, amount: extra.pickup.fee }] : []),
  ];
  return {
    source,
    carrier,
    rate_id,
    currency: "EUR",
    total: round(breakdown.reduce((sum, b) => sum + b.amount, 0)),
    transit_days,
    valid_until: t("23:59:00"),
    chargeable_weight_kg: cw,
    breakdown,
  };
}
const round = (n: number) => Math.round(n * 100) / 100;
const sent = (o: PriceOption, at: string) => ({ ...o, sent_at: t(at) });

// ── #17 Huber · MUC → JFK · fastest, door pickup ──────────────────────────
const z2 = { zone: "Z2", fee: 65 };
const s17 = {
  lh: rate("carrier_bid", "Lufthansa Cargo", "R-88213", 481, 3.05, 1, { pickup: z2 }),
  de: rate("sheet", "Delta Cargo", "SHT-DL-MUC-US", 481, 2.48, 3, { pickup: z2 }),
  ua: rate("portal", "United Cargo", "R-88220", 481, 2.71, 2, { pickup: z2 }),
  de4: rate("carrier_bid", "Condor Cargo", "R-88219", 481, 2.56, 3, { pickup: z2 }),
};
// Trucker bid for the door-to-port leg (leg "pickup"): added to an air option, never compared with them.
const s17pickup: PriceOption = {
  source: "carrier_bid", leg: "pickup", carrier: "Huber Transporte", rate_id: "T-4471", currency: "EUR",
  total: 85, transit_days: 0, valid_until: t("23:59:00"), chargeable_weight_kg: 481, breakdown: [],
};
// ── #16 Brennwald · FRA → SIN · cheapest, airport delivery ────────────────
const s16 = {
  sq: rate("sheet", "Singapore Airlines Cargo", "SHT-SQ-FRA-SIN", 420, 2.39, 2),
  cx: rate("portal", "Cathay Cargo", "R-88190", 420, 2.31, 3),
  tk: rate("carrier_bid", "Turkish Cargo", "R-88194", 420, 2.36, 4),
};
// ── #15 Lago · MXP → DXB · fastest, door pickup ───────────────────────────
const s15 = {
  ek: rate("carrier_bid", "Emirates SkyCargo", "R-88150", 108, 2.42, 1, { pickup: { zone: "Z1", fee: 45 } }),
  qr: rate("portal", "Qatar Airways Cargo", "R-88151", 108, 2.18, 2, { pickup: { zone: "Z1", fee: 45 } }),
};
// ── #12 Vetro Bavaria · MUC → LAX · cheapest ──────────────────────────────
const s12 = {
  aa: rate("sheet", "American Airlines Cargo", "SHT-AA-MUC-LAX", 310, 2.74, 3),
  lh: rate("portal", "Lufthansa Cargo", "R-88111", 310, 2.69, 2),
  af: rate("carrier_bid", "Air France KLM Cargo", "R-88114", 310, 2.81, 3),
};
// ── #11 Kessler Optik · STR → BOS · cheapest ──────────────────────────────
const s11 = {
  ba: rate("portal", "IAG Cargo", "R-88096", 96, 3.12, 2),
  lh: rate("sheet", "Lufthansa Cargo", "SHT-LH-STR-US", 96, 3.28, 1),
};
// ── #10 Rhein Feinmechanik · FRA → GRU · cheapest ────────────────────────
const s10 = {
  la: rate("sheet", "LATAM Cargo", "SHT-LA-FRA-GRU", 655, 2.21, 3),
  lh: rate("portal", "Lufthansa Cargo", "R-88072", 655, 2.34, 2),
  af: rate("carrier_bid", "Air France KLM Cargo", "R-88075", 655, 2.18, 4),
  tp: rate("carrier_bid", "TAP Air Cargo", "R-88077", 655, 2.29, 3),
};
// ── #9 Tanaka · DUS → NRT · fastest ──────────────────────────────────────
const s9 = {
  nh: rate("carrier_bid", "ANA Cargo", "R-88051", 205, 3.36, 1),
  jl: rate("portal", "JAL Cargo", "R-88050", 205, 3.18, 2),
};
// ── #8 Alpenmilch · MUC → HKG · cheapest ─────────────────────────────────
const s8 = {
  cx: rate("portal", "Cathay Cargo", "R-88031", 240, 2.52, 2),
  lh: rate("sheet", "Lufthansa Cargo", "SHT-LH-MUC-HKG", 240, 2.66, 1),
  ek: rate("carrier_bid", "Emirates SkyCargo", "R-88034", 240, 2.58, 3),
};
// ── #7 Fischer Orgelbau · MUC → YYZ · cheapest, door pickup ──────────────
const s7 = {
  ac: rate("portal", "Air Canada Cargo", "R-88012", 372, 2.44, 2, { pickup: { zone: "Z3", fee: 85 } }),
  lh: rate("sheet", "Lufthansa Cargo", "SHT-LH-MUC-CA", 372, 2.57, 1, { pickup: { zone: "Z3", fee: 85 } }),
};

// Defaults for a session that has not got that far yet; fresh arrays per session.
const base = (): Pick<Session, "bids" | "quote" | "booking" | "status_updates" | "needs_human" | "paused"> => ({
  bids: [],
  quote: null,
  booking: null,
  status_updates: [],
  needs_human: false,
  paused: false,
});

export const mockSessions: Session[] = [
  {
    ...base(),
    id: 18,
    customer: "Atelier Rousseau",
    thread_id: "th-18",
    received_at: t("02:06:00"),
    stage: "new",
    outcome: "open",
    rfq: null,
    llm_cost_usd: 0,
  },
  {
    ...base(),
    id: 17,
    customer: "Huber Maschinenbau GmbH",
    thread_id: "th-17",
    received_at: t("02:00:00"),
    stage: "quoted",
    outcome: "open",
    rfq: {
      origin: "MUC",
      destination: "JFK",
      ask: "fastest",
      pickup: { address: "Lindwurmstraße 12, 80337 München", zone: "Z2" },
      ready_date: "2026-11-23",
      pieces: [{ count: 3, length_cm: 120, width_cm: 80, height_cm: 100, weight_kg: 140 }],
      commodity: "machine parts",
      dangerous_goods: false,
      customer_reference: "PO-4711",
      language: "de",
    },
    bids: [s17.de, s17.ua, s17.de4, s17.lh, s17pickup],
    quote: sent(s17.lh, "02:01:32"),
    llm_cost_usd: 0.0002,
  },
  {
    ...base(),
    id: 16,
    customer: "Brennwald Pharma AG",
    thread_id: "th-16",
    received_at: t("01:54:00"),
    stage: "booked",
    outcome: "won",
    rfq: {
      origin: "FRA",
      destination: "SIN",
      ask: "cheapest",
      pickup: null,
      ready_date: "2026-11-24",
      pieces: [{ count: 2, length_cm: 100, width_cm: 120, height_cm: 90, weight_kg: 210 }],
      commodity: "medical devices",
      dangerous_goods: false,
      customer_reference: "BP-2291",
      language: "en",
    },
    bids: [s16.sq, s16.cx, s16.tk],
    quote: sent(s16.cx, "01:55:41"),
    booking: { rate_id: "R-88190", confirmation: "160-48213377", booking_reference: "LX-16-0412", airline: "Cathay Cargo", status: "confirmed", booked_at: t("02:03:10") },
    status_updates: [{ at: t("02:03:20"), text: "Booking confirmed, AWB 160-48213377, CX 288 on 24 Nov" }],
    llm_cost_usd: 0.00018,
  },
  {
    ...base(),
    id: 15,
    customer: "Lago Fashion S.r.l.",
    thread_id: "th-15",
    received_at: t("01:48:00"),
    stage: "tracking",
    outcome: "won",
    rfq: {
      origin: "MXP",
      destination: "DXB",
      ask: "fastest",
      pickup: { address: "Via Tortona 31, 20144 Milano", zone: "Z1" },
      ready_date: "2026-11-22",
      pieces: [{ count: 6, length_cm: 60, width_cm: 40, height_cm: 40, weight_kg: 18 }],
      commodity: "garments",
      dangerous_goods: false,
      customer_reference: "LF-9902",
      language: "it",
    },
    bids: [s15.qr, s15.ek],
    quote: sent(s15.ek, "01:49:12"),
    booking: { rate_id: "R-88150", confirmation: "176-90012345", booking_reference: "LX-15-0388", airline: "Emirates SkyCargo", status: "in transit", booked_at: t("01:52:00") },
    status_updates: [
      { at: t("01:52:10"), text: "Booking confirmed, AWB 176-90012345" },
      { at: t("02:04:00"), text: "Picked up in zone Z1, at MXP for EK 092" },
    ],
    llm_cost_usd: 0.00021,
  },
  {
    ...base(),
    id: 14,
    customer: "Nordlicht Batterien KG",
    thread_id: "th-14",
    received_at: t("01:42:00"),
    stage: "pricing",
    outcome: "open",
    rfq: {
      origin: "HAM",
      destination: "ORD",
      ask: "cheapest",
      pickup: { address: "Am Sandtorkai 5, 20457 Hamburg", zone: null },
      ready_date: "2026-11-23",
      pieces: [{ count: 4, length_cm: 80, width_cm: 60, height_cm: 70, weight_kg: 95 }],
      commodity: "lithium-ion batteries (UN3480)",
      dangerous_goods: true,
      customer_reference: null,
      language: "de",
    },
    llm_cost_usd: 0.00019,
    needs_human: true,
    paused: true,
  },
  {
    ...base(),
    id: 13,
    customer: "Kowalski Elektronik Sp. z o.o.",
    thread_id: "th-13",
    received_at: t("01:36:00"),
    stage: "failed",
    outcome: "expired",
    rfq: {
      origin: "MUC",
      destination: "PVG",
      ask: "cheapest",
      pickup: null,
      ready_date: "2026-11-22",
      pieces: [{ count: 1, length_cm: 120, width_cm: 100, height_cm: 110, weight_kg: 260 }],
      commodity: "electronic components",
      dangerous_goods: false,
      customer_reference: "KE-118",
      language: "en",
    },
    llm_cost_usd: 0.0002,
  },
  {
    ...base(),
    id: 12,
    customer: "Vetro Bavaria GmbH",
    thread_id: "th-12",
    received_at: t("01:30:00"),
    stage: "done",
    outcome: "lost",
    rfq: {
      origin: "MUC",
      destination: "LAX",
      ask: "cheapest",
      pickup: null,
      ready_date: "2026-11-25",
      pieces: [{ count: 2, length_cm: 110, width_cm: 70, height_cm: 120, weight_kg: 120 }],
      commodity: "art glass, crated",
      dangerous_goods: false,
      customer_reference: "VB-0331",
      language: "de",
    },
    bids: [s12.aa, s12.lh, s12.af],
    quote: sent(s12.lh, "01:31:55"),
    llm_cost_usd: 0.00022,
  },
  {
    ...base(),
    id: 11,
    customer: "Kessler Optik GmbH",
    thread_id: "th-11",
    received_at: t("01:24:00"),
    stage: "booked",
    outcome: "won",
    rfq: {
      origin: "STR",
      destination: "BOS",
      ask: "cheapest",
      pickup: null,
      ready_date: "2026-11-24",
      pieces: [{ count: 2, length_cm: 60, width_cm: 50, height_cm: 40, weight_kg: 38 }],
      commodity: "optical lenses",
      dangerous_goods: false,
      customer_reference: "KO-5520",
      language: "de",
    },
    bids: [s11.ba, s11.lh],
    quote: sent(s11.ba, "01:26:48"),
    booking: { rate_id: "R-88096", confirmation: "125-77310942", booking_reference: "LX-11-0301", airline: "IAG Cargo", status: "confirmed", booked_at: t("01:41:30") },
    status_updates: [{ at: t("01:41:40"), text: "Booking confirmed, AWB 125-77310942" }],
    llm_cost_usd: 0.00031,
  },
  {
    ...base(),
    id: 10,
    customer: "Rhein Feinmechanik AG",
    thread_id: "th-10",
    received_at: t("01:18:00"),
    stage: "quoted",
    outcome: "open",
    rfq: {
      origin: "FRA",
      destination: "GRU",
      ask: "cheapest",
      pickup: null,
      ready_date: "2026-11-24",
      pieces: [
        { count: 3, length_cm: 120, width_cm: 80, height_cm: 110, weight_kg: 160 },
        { count: 1, length_cm: 80, width_cm: 60, height_cm: 60, weight_kg: 45 },
      ],
      commodity: "precision tooling",
      dangerous_goods: false,
      customer_reference: "RF-77-12",
      language: "de",
    },
    bids: [s10.la, s10.lh, s10.af, s10.tp],
    quote: sent(s10.af, "01:19:38"),
    llm_cost_usd: 0.00024,
    needs_human: true,
  },
  {
    ...base(),
    id: 9,
    customer: "Tanaka Precision Europe B.V.",
    thread_id: "th-9",
    received_at: t("01:12:00"),
    stage: "done",
    outcome: "expired",
    rfq: {
      origin: "DUS",
      destination: "NRT",
      ask: "fastest",
      pickup: null,
      ready_date: "2026-11-22",
      pieces: [{ count: 1, length_cm: 100, width_cm: 80, height_cm: 90, weight_kg: 205 }],
      volume_m3: 0.72,
      commodity: "spare parts, AOG",
      dangerous_goods: false,
      customer_reference: "TP-AOG-09",
      language: "en",
    },
    bids: [s9.jl, s9.nh],
    quote: sent(s9.nh, "01:13:22"),
    llm_cost_usd: 0.00017,
  },
  {
    ...base(),
    id: 8,
    customer: "Alpenmilch Export eG",
    thread_id: "th-8",
    received_at: t("01:06:00"),
    stage: "done",
    outcome: "won",
    rfq: {
      origin: "MUC",
      destination: "HKG",
      ask: "cheapest",
      pickup: null,
      ready_date: "2026-11-22",
      pieces: [{ count: 2, length_cm: 120, width_cm: 80, height_cm: 75, weight_kg: 115 }],
      commodity: "cheese samples, chilled",
      dangerous_goods: false,
      customer_reference: "AM-2611",
      language: "de",
    },
    bids: [s8.cx, s8.lh, s8.ek],
    quote: sent(s8.cx, "01:07:29"),
    booking: { rate_id: "R-88031", confirmation: "160-48199021", booking_reference: "LX-08-0207", airline: "Cathay Cargo", status: "confirmed", booked_at: t("01:20:05") },
    status_updates: [{ at: t("01:20:15"), text: "Booking confirmed, AWB 160-48199021" }],
    llm_cost_usd: 0.00019,
  },
  {
    ...base(),
    id: 7,
    customer: "Fischer Orgelbau",
    thread_id: "th-7",
    received_at: t("01:00:00"),
    stage: "done",
    outcome: "won",
    rfq: {
      origin: "MUC",
      destination: "YYZ",
      ask: "cheapest",
      pickup: { address: "Kirchplatz 4, 82131 Gauting", zone: "Z3" },
      ready_date: "2026-11-23",
      pieces: [{ count: 1, length_cm: 240, width_cm: 60, height_cm: 50, weight_kg: 62 }],
      commodity: "organ pipes, crated",
      dangerous_goods: false,
      customer_reference: null,
      language: "de",
    },
    bids: [s7.ac, s7.lh],
    quote: sent(s7.ac, "01:01:05"),
    booking: { rate_id: "R-88012", confirmation: "014-22018834", booking_reference: "LX-07-0150", airline: "Air Canada Cargo", status: "confirmed", booked_at: t("01:15:40") },
    status_updates: [{ at: t("01:15:50"), text: "Booking confirmed, AWB 014-22018834" }],
    llm_cost_usd: 0.00016,
  },
];

const OURS = "quotes@leylu.air";

const mail = (session_id: number, at: string, kind: Event["kind"], text: string, from: string, to: string, subject: string, body: string): Event => ({
  session_id,
  at: t(at),
  kind,
  text,
  data: { from, to, subject, body },
  llm_cost_usd: 0,
});
const step = (session_id: number, at: string, kind: Event["kind"], text: string, llm_cost_usd = 0): Event => ({
  session_id,
  at: t(at),
  kind,
  text,
  data: {},
  llm_cost_usd,
});

export const mockEvents: Event[] = [
  // #18 — just arrived
  mail(18, "02:06:00", "mail_in", "RFQ from Atelier Rousseau", "contact@atelier-rousseau.fr", OURS, "Devis fret aérien CDG → YUL",
    "Bonjour,\n\nPourriez-vous me faire un devis pour 2 colis de 50 × 50 × 60 cm, 22 kg chacun, de Paris CDG à Montréal ? Le moins cher possible, ce n'est pas urgent.\n\nMerci d'avance,\nClaire Rousseau"),
  step(18, "02:06:01", "routed", "Routed: new customer RFQ, new thread"),

  // #17 — quoted, waiting for the customer
  mail(17, "02:00:00", "mail_in", "RFQ from Huber Maschinenbau", "m.huber@huber-maschinenbau.de", OURS, "Anfrage Luftfracht MUC → JFK",
    "Guten Morgen,\n\nwir brauchen ein Angebot für 3 Kisten à 120 × 80 × 100 cm, je 140 kg. Abholung Lindwurmstraße 12, München, ab Montag. Ziel New York JFK, so schnell wie möglich.\n\nReferenz PO-4711.\n\nDanke und Gruß\nMarkus Huber"),
  step(17, "02:00:01", "routed", "Routed: new customer RFQ, new thread"),
  step(17, "02:00:03", "extracted", "Extracted: MUC → JFK, 3 pcs, 420 kg actual / 481 kg chargeable, fastest, pickup zone Z2", 0.0002),
  step(17, "02:00:05", "priced", `Sheet + portal: best ${eur(s17.de.total)} Delta (3 days), fastest ${eur(s17.ua.total)} United (2 days)`),
  step(17, "02:00:06", "carrier_asked", "Asked 4 carriers for bids (fastest requested)"),
  step(17, "02:00:48", "bid", `Bid: Condor Cargo ${eur(s17.de4.total)}, 3 days`),
  step(17, "02:01:10", "bid", `Bid: Lufthansa Cargo ${eur(s17.lh.total)}, 1 day`),
  step(17, "02:01:25", "carrier_asked", "Closed bidding: 2 of 4 carriers answered within 80 s"),
  mail(17, "02:01:32", "quote_sent", `Quote sent: ${eur(s17.lh.total)} all-in, fastest`, OURS, "m.huber@huber-maschinenbau.de", "Re: Anfrage Luftfracht MUC → JFK",
    `Guten Morgen Herr Huber,\n\ndanke für Ihre Anfrage. Für die 3 Kisten (481 kg frachtpflichtig) ab Lindwurmstraße nach New York JFK ist die schnellste Option Lufthansa Cargo mit 1 Tag Laufzeit.\n\nGesamtpreis inkl. Abholung, Treibstoff, Sicherheit und AWB: ${eur(s17.lh.total)} all-in, gültig bis heute 23:59.\n\nSagen Sie einfach Bescheid, dann buchen wir sofort.\n\nViele Grüße\nIhr Leylü Team`),

  // #16 — booked
  mail(16, "01:54:00", "mail_in", "RFQ from Brennwald Pharma", "anna.keller@brennwald.ch", OURS, "Air freight FRA-SIN",
    "Hi,\n\nplease quote 2 pallets 100x120x90, 210 kg each, delivered to FRA airport, to Singapore. Cheapest option please.\n\nRef BP-2291\n\nKind regards,\nAnna"),
  step(16, "01:54:01", "routed", "Routed: new customer RFQ, new thread"),
  step(16, "01:54:03", "extracted", "Extracted: FRA → SIN, 2 pcs, 420 kg chargeable, cheapest, airport delivery", 0.00018),
  step(16, "01:54:06", "priced", `Sheet + portal: best ${eur(s16.cx.total)} Cathay (portal, 3 days)`),
  step(16, "01:54:07", "carrier_asked", "Asked 3 carriers for bids"),
  step(16, "01:55:20", "bid", `Bid: Turkish Cargo ${eur(s16.tk.total)}, 4 days`),
  mail(16, "01:55:41", "quote_sent", `Quote sent: ${eur(s16.cx.total)} all-in, cheapest`, OURS, "anna.keller@brennwald.ch", "Re: Air freight FRA-SIN",
    `Hi Anna,\n\nthanks for reaching out. The best price for your 2 pallets FRA → SIN is with Cathay Cargo, 3 days in transit.\n\nAll-in total: ${eur(s16.cx.total)}, valid until tonight 23:59.\n\nJust reply and we'll book it right away.\n\nBest,\nLeylü`),
  mail(16, "02:03:00", "accepted", "Customer accepted", "anna.keller@brennwald.ch", OURS, "Re: Air freight FRA-SIN", "Great, please book.\n\nAnna"),
  step(16, "02:03:10", "booked", "Booked rate R-88190 on the portal: AWB 160-48213377"),
  mail(16, "02:03:20", "status_sent", "Booking confirmation sent", OURS, "anna.keller@brennwald.ch", "Re: Air freight FRA-SIN",
    "Hi Anna,\n\nyou're booked: Cathay Cargo CX 288 on 24 Nov, AWB 160-48213377. We'll keep you posted.\n\nBest,\nLeylü"),

  // #15 — booked, now answering tracking
  mail(15, "01:48:00", "mail_in", "RFQ from Lago Fashion", "spedizioni@lagofashion.it", OURS, "Richiesta quotazione MXP-DXB",
    "Buongiorno,\n\nci serve una quotazione urgente per 6 colli 60x40x40, 18 kg l'uno, ritiro in Via Tortona 31, Milano, destinazione Dubai. Il più veloce possibile.\n\nRif. LF-9902\n\nGrazie,\nGiulia"),
  step(15, "01:48:01", "routed", "Routed: new customer RFQ, new thread"),
  step(15, "01:48:03", "extracted", "Extracted: MXP → DXB, 6 pcs, 108 kg chargeable, fastest, pickup zone Z1", 0.00021),
  step(15, "01:48:05", "priced", `Portal: Qatar ${eur(s15.qr.total)}, 2 days`),
  step(15, "01:48:06", "carrier_asked", "Asked 2 carriers for bids (fastest requested)"),
  step(15, "01:49:02", "bid", `Bid: Emirates SkyCargo ${eur(s15.ek.total)}, 1 day`),
  mail(15, "01:49:12", "quote_sent", `Quote sent: ${eur(s15.ek.total)} all-in, fastest`, OURS, "spedizioni@lagofashion.it", "Re: Richiesta quotazione MXP-DXB",
    `Buongiorno Giulia,\n\ngrazie per la richiesta. L'opzione più veloce è Emirates SkyCargo, 1 giorno di transito, ritiro incluso in Via Tortona.\n\nPrezzo totale all-in: ${eur(s15.ek.total)}.\n\nCi scriva pure e prenotiamo subito.\n\nCordiali saluti,\nLeylü`),
  mail(15, "01:51:40", "accepted", "Customer accepted", "spedizioni@lagofashion.it", OURS, "Re: Richiesta quotazione MXP-DXB", "Perfetto, procedete.\n\nGiulia"),
  step(15, "01:52:00", "booked", "Booked rate R-88150 on the portal: AWB 176-90012345"),
  mail(15, "01:52:10", "status_sent", "Booking confirmation sent", OURS, "spedizioni@lagofashion.it", "Re: Richiesta quotazione MXP-DXB",
    "Buongiorno Giulia,\n\nprenotato: Emirates SkyCargo, AWB 176-90012345. Il ritiro è previsto entro stanotte.\n\nCordiali saluti,\nLeylü"),
  mail(15, "02:03:45", "mail_in", "Tracking question", "spedizioni@lagofashion.it", OURS, "Dov'è LF-9902?", "Buongiorno, a che punto è la spedizione LF-9902?\n\nGiulia"),
  step(15, "02:03:47", "routed", "Routed: tracking question on a booked shipment"),
  mail(15, "02:04:00", "tracking_answer", "Tracking answered from CRM", OURS, "spedizioni@lagofashion.it", "Re: Dov'è LF-9902?",
    "Buongiorno Giulia,\n\nLF-9902 (AWB 176-90012345) è stata ritirata a Milano ed è a MXP, prenotata sul volo EK 092.\n\nCordiali saluti,\nLeylü"),

  // #14 — needs a person, paused
  mail(14, "01:42:00", "mail_in", "RFQ from Nordlicht Batterien", "versand@nordlicht-batterien.de", OURS, "Angebot Luftfracht HAM → Chicago",
    "Hallo,\n\nbitte ein Angebot für 4 Kartons Lithium-Ionen-Akkus (UN3480), je 80 × 60 × 70 cm und 95 kg. Abholung bei uns am Sandtorkai, Ziel Chicago O'Hare. Günstigste Variante.\n\nGrüße\nJ. Petersen"),
  step(14, "01:42:01", "routed", "Routed: new customer RFQ, new thread"),
  step(14, "01:42:03", "extracted", "Extracted: HAM → ORD, 4 pcs, lithium-ion batteries (UN3480), cheapest", 0.00019),
  step(14, "01:42:04", "needs_human", "Dangerous goods (UN3480) and no pickup zone for Sandtorkai: needs a person"),
  step(14, "01:42:04", "intervened", "Session paused automatically until a person takes over"),

  // #13 — failed
  mail(13, "01:36:00", "mail_in", "RFQ from Kowalski Elektronik", "export@kowalski-elektronik.pl", OURS, "Quote MUC-PVG, 1 crate",
    "Hello,\n\nwe need the cheapest price for 1 crate 120x100x110 cm, 260 kg, from Munich airport to Shanghai PVG. Ready tomorrow.\n\nRef KE-118\nPiotr"),
  step(13, "01:36:01", "routed", "Routed: new customer RFQ, new thread"),
  step(13, "01:36:03", "extracted", "Extracted: MUC → PVG, 1 pc, 260 kg actual / 220 kg volume, cheapest", 0.0002),
  step(13, "01:36:05", "error", "Rate portal answered 429 (rate limit), retrying with backoff"),
  step(13, "01:36:06", "carrier_asked", "Asked 3 carriers for bids"),
  step(13, "01:42:00", "error", "No price within 6:00: portal still rate-limited, no carrier answered"),

  // #12 — lost
  mail(12, "01:30:00", "mail_in", "RFQ from Vetro Bavaria", "logistik@vetro-bavaria.de", OURS, "Kunstglas nach Los Angeles",
    "Servus,\n\nzwei Kisten Kunstglas, je 110 × 70 × 120 cm und 120 kg, ab Flughafen München nach LAX. Am liebsten günstig.\n\nRef VB-0331\n\nDanke, Lena Brandl"),
  step(12, "01:30:01", "routed", "Routed: new customer RFQ, new thread"),
  step(12, "01:30:03", "extracted", "Extracted: MUC → LAX, 2 pcs, 310 kg chargeable, cheapest, airport delivery", 0.00022),
  step(12, "01:30:05", "priced", `Sheet + portal: best ${eur(s12.lh.total)} Lufthansa (portal, 2 days)`),
  step(12, "01:30:06", "carrier_asked", "Asked 3 carriers for bids"),
  step(12, "01:31:30", "bid", `Bid: Air France KLM Cargo ${eur(s12.af.total)}, 3 days`),
  mail(12, "01:31:55", "quote_sent", `Quote sent: ${eur(s12.lh.total)} all-in, cheapest`, OURS, "logistik@vetro-bavaria.de", "Re: Kunstglas nach Los Angeles",
    `Servus Frau Brandl,\n\nfür Ihre zwei Kisten nach LAX ist Lufthansa Cargo am günstigsten, 2 Tage Laufzeit.\n\nGesamtpreis all-in: ${eur(s12.lh.total)}.\n\nMelden Sie sich einfach, dann buchen wir.\n\nViele Grüße\nIhr Leylü Team`),
  mail(12, "01:58:10", "mail_in", "Customer declined", "logistik@vetro-bavaria.de", OURS, "Re: Kunstglas nach Los Angeles",
    "Danke, wir haben leider ein günstigeres Angebot bekommen und gehen diesmal woanders hin.\n\nLena Brandl"),
  step(12, "01:58:11", "routed", "Routed: customer declined, session closed as lost"),

  // #11 — a person stepped in, then booked
  mail(11, "01:24:00", "mail_in", "RFQ from Kessler Optik", "a.kessler@kessler-optik.de", OURS, "Luftfracht STR → Boston, mit Versicherung?",
    "Hallo,\n\nzwei Kartons Linsen, je 60 × 50 × 40 cm und 38 kg, ab Stuttgart Flughafen nach Boston. Günstigste Variante. Können Sie die Sendung auch versichern?\n\nGruß\nAndrea Kessler"),
  step(11, "01:24:01", "routed", "Routed: new customer RFQ, new thread"),
  step(11, "01:24:03", "extracted", "Extracted: STR → BOS, 2 pcs, 96 kg chargeable, cheapest; asks about cargo insurance", 0.00031),
  step(11, "01:24:05", "priced", `Sheet + portal: best ${eur(s11.ba.total)} IAG (portal, 2 days)`),
  step(11, "01:24:05", "needs_human", "Insurance question has no rule: needs a person before the quote goes out"),
  step(11, "01:26:30", "intervened", "Operator edited the reply (insurance line added) and sent it"),
  mail(11, "01:26:48", "quote_sent", `Quote sent by hand: ${eur(s11.ba.total)} all-in, cheapest`, OURS, "a.kessler@kessler-optik.de", "Re: Luftfracht STR → Boston, mit Versicherung?",
    `Hallo Frau Kessler,\n\nfür Ihre zwei Kartons nach Boston ist IAG Cargo am günstigsten, 2 Tage Laufzeit.\n\nGesamtpreis all-in: ${eur(s11.ba.total)}. Eine Transportversicherung bieten wir gern separat an; dafür bräuchten wir nur den Warenwert.\n\nViele Grüße\nIhr Leylü Team`),
  mail(11, "01:41:00", "accepted", "Customer accepted", "a.kessler@kessler-optik.de", OURS, "Re: Luftfracht STR → Boston, mit Versicherung?", "Passt, bitte buchen. Versicherung brauchen wir doch nicht.\n\nA. Kessler"),
  step(11, "01:41:30", "booked", "Booked rate R-88096 on the portal: AWB 125-77310942"),
  mail(11, "01:41:40", "status_sent", "Booking confirmation sent", OURS, "a.kessler@kessler-optik.de", "Re: Luftfracht STR → Boston, mit Versicherung?",
    "Hallo Frau Kessler,\n\nist gebucht: IAG Cargo, AWB 125-77310942.\n\nViele Grüße\nIhr Leylü Team"),

  // #10 — quoted, then an unclear reply: needs a person
  mail(10, "01:18:00", "mail_in", "RFQ from Rhein Feinmechanik", "dispo@rhein-feinmechanik.de", OURS, "Anfrage FRA → São Paulo",
    "Guten Tag,\n\nbitte um Angebot für 3 Kisten 120 × 80 × 110 cm à 160 kg und 1 Karton 80 × 60 × 60 cm, 45 kg. Anlieferung FRA, Ziel GRU. Preis ist wichtiger als Zeit.\n\nUnsere Ref.: RF-77-12\n\nMit freundlichen Grüßen\nT. Wagner"),
  step(10, "01:18:01", "routed", "Routed: new customer RFQ, new thread"),
  step(10, "01:18:03", "extracted", "Extracted: FRA → GRU, 4 pcs, 525 kg actual / 655 kg chargeable, cheapest", 0.00024),
  step(10, "01:18:05", "priced", `Sheet + portal: best ${eur(s10.la.total)} LATAM (sheet, 3 days)`),
  step(10, "01:18:06", "carrier_asked", "Asked 5 carriers for bids"),
  step(10, "01:19:01", "bid", `Bid: TAP Air Cargo ${eur(s10.tp.total)}, 3 days`),
  step(10, "01:19:20", "bid", `Bid: Air France KLM Cargo ${eur(s10.af.total)}, 4 days`),
  mail(10, "01:19:38", "quote_sent", `Quote sent: ${eur(s10.af.total)} all-in, cheapest`, OURS, "dispo@rhein-feinmechanik.de", "Re: Anfrage FRA → São Paulo",
    `Guten Tag Herr Wagner,\n\nvielen Dank für Ihre Anfrage. Am günstigsten fliegt Ihre Sendung (655 kg frachtpflichtig) mit Air France KLM Cargo, 4 Tage Laufzeit.\n\nGesamtpreis all-in: ${eur(s10.af.total)}, gültig bis heute 23:59.\n\nGeben Sie uns kurz Bescheid, dann buchen wir.\n\nMit freundlichen Grüßen\nIhr Leylü Team`),
  mail(10, "01:52:30", "mail_in", "Customer reply: split shipment?", "dispo@rhein-feinmechanik.de", OURS, "Re: Anfrage FRA → São Paulo",
    "Danke. Können wir den Karton schon morgen schicken und die drei Kisten erst nächste Woche? Was kostet das dann?\n\nT. Wagner"),
  step(10, "01:52:32", "routed", "Routed: reply asks to split the shipment over two dates"),
  step(10, "01:52:33", "needs_human", "Split shipment with two ready dates is outside the quote rules: needs a person"),

  // #9 — expired
  mail(9, "01:12:00", "mail_in", "RFQ from Tanaka Precision", "ops@tanaka-precision.eu", OURS, "URGENT AOG DUS-NRT",
    "Hi team,\n\nAOG spare part, 1 crate 100x80x90 cm, 205 kg, 0.72 cbm. Düsseldorf airport to Tokyo Narita, fastest possible.\n\nRef TP-AOG-09\n\nThanks, Kenji"),
  step(9, "01:12:01", "routed", "Routed: new customer RFQ, new thread"),
  step(9, "01:12:03", "extracted", "Extracted: DUS → NRT, 1 pc, 205 kg chargeable, fastest", 0.00017),
  step(9, "01:12:05", "priced", `Portal: JAL ${eur(s9.jl.total)}, 2 days`),
  step(9, "01:12:06", "carrier_asked", "Asked 2 carriers for bids (fastest requested)"),
  step(9, "01:13:10", "bid", `Bid: ANA Cargo ${eur(s9.nh.total)}, 1 day`),
  mail(9, "01:13:22", "quote_sent", `Quote sent: ${eur(s9.nh.total)} all-in, fastest`, OURS, "ops@tanaka-precision.eu", "Re: URGENT AOG DUS-NRT",
    `Hi Kenji,\n\nfastest option for your AOG crate is ANA Cargo, 1 day DUS → NRT.\n\nAll-in total: ${eur(s9.nh.total)}, valid until tonight 23:59.\n\nReply and we'll book it straight away.\n\nBest,\nLeylü`),

  // #8 — won, done
  mail(8, "01:06:00", "mail_in", "RFQ from Alpenmilch Export", "export@alpenmilch.de", OURS, "Muster nach Hongkong",
    "Hallo,\n\nwir möchten 2 Paletten Käsemuster (gekühlt, 120 × 80 × 75 cm, je 115 kg) ab MUC nach Hongkong schicken. Möglichst günstig.\n\nRef AM-2611\n\nBeste Grüße\nSophie Maier"),
  step(8, "01:06:01", "routed", "Routed: new customer RFQ, new thread"),
  step(8, "01:06:03", "extracted", "Extracted: MUC → HKG, 2 pcs, 240 kg chargeable, cheapest, chilled", 0.00019),
  step(8, "01:06:05", "priced", `Sheet + portal: best ${eur(s8.cx.total)} Cathay (portal, 2 days)`),
  step(8, "01:06:06", "carrier_asked", "Asked 3 carriers for bids"),
  step(8, "01:07:10", "bid", `Bid: Emirates SkyCargo ${eur(s8.ek.total)}, 3 days`),
  mail(8, "01:07:29", "quote_sent", `Quote sent: ${eur(s8.cx.total)} all-in, cheapest`, OURS, "export@alpenmilch.de", "Re: Muster nach Hongkong",
    `Hallo Frau Maier,\n\nam günstigsten kommen Ihre Muster mit Cathay Cargo nach Hongkong, 2 Tage Laufzeit.\n\nGesamtpreis all-in: ${eur(s8.cx.total)}.\n\nKurze Antwort genügt, dann buchen wir.\n\nBeste Grüße\nIhr Leylü Team`),
  mail(8, "01:19:50", "accepted", "Customer accepted", "export@alpenmilch.de", OURS, "Re: Muster nach Hongkong", "Super, bitte buchen!\n\nSophie Maier"),
  step(8, "01:20:05", "booked", "Booked rate R-88031 on the portal: AWB 160-48199021"),
  mail(8, "01:20:15", "status_sent", "Booking confirmation sent", OURS, "export@alpenmilch.de", "Re: Muster nach Hongkong",
    "Hallo Frau Maier,\n\nist gebucht: Cathay Cargo, AWB 160-48199021.\n\nBeste Grüße\nIhr Leylü Team"),

  // #7 — won, done
  mail(7, "01:00:00", "mail_in", "RFQ from Fischer Orgelbau", "werkstatt@fischer-orgelbau.de", OURS, "Orgelpfeifen nach Toronto",
    "Guten Abend,\n\neine lange Kiste mit Orgelpfeifen, 240 × 60 × 50 cm, 62 kg. Abholung in Gauting, Kirchplatz 4, nach Toronto. Gern die günstigste Lösung.\n\nHerzliche Grüße\nThomas Fischer"),
  step(7, "01:00:01", "routed", "Routed: new customer RFQ, new thread"),
  step(7, "01:00:03", "extracted", "Extracted: MUC → YYZ, 1 pc, 62 kg actual / 120 kg volume, cheapest, pickup zone Z3", 0.00016),
  step(7, "01:00:05", "priced", `Sheet + portal: best ${eur(s7.ac.total)} Air Canada (portal, 2 days)`),
  mail(7, "01:01:05", "quote_sent", `Quote sent: ${eur(s7.ac.total)} all-in, cheapest`, OURS, "werkstatt@fischer-orgelbau.de", "Re: Orgelpfeifen nach Toronto",
    `Guten Abend Herr Fischer,\n\nam günstigsten reist Ihre Kiste mit Air Canada Cargo nach Toronto, 2 Tage Laufzeit, Abholung in Gauting inklusive.\n\nGesamtpreis all-in: ${eur(s7.ac.total)}.\n\nEine kurze Antwort genügt, dann buchen wir.\n\nHerzliche Grüße\nIhr Leylü Team`),
  mail(7, "01:15:20", "accepted", "Customer accepted", "werkstatt@fischer-orgelbau.de", OURS, "Re: Orgelpfeifen nach Toronto", "Gern, bitte buchen.\n\nT. Fischer"),
  step(7, "01:15:40", "booked", "Booked rate R-88012 on the portal: AWB 014-22018834"),
  mail(7, "01:15:50", "status_sent", "Booking confirmation sent", OURS, "werkstatt@fischer-orgelbau.de", "Re: Orgelpfeifen nach Toronto",
    "Guten Abend Herr Fischer,\n\nist gebucht: Air Canada Cargo, AWB 014-22018834. Die Abholung in Gauting kommt morgen früh.\n\nHerzliche Grüße\nIhr Leylü Team"),
];
