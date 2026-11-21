# KIT_SUMMARY.md: 5U start kit, API and how it maps to our repo

> Written Sat 21 Nov 2026 ~14:45 from the 5U start kit (`GET /kit/start-kit.zip`), `GET /openapi.json` and read-only API snapshots.
> Local copies (not in git): `kit/start-kit/`, `kit/openapi.json`, `kit/api-snapshots/*.json`, and all 10 sheets normalized into one file: `kit/tariffs.normalized.json`.
> Every rate table below was generated from that normalized file (parsed by code, Danube transcribed from the photos and cross-checked with OCR), not typed by hand.

## 0. The ten facts that matter most

1. **Volume weight: 1 cbm = 167 kg** in every sheet and on the portal (`chargeable = max(actual kg, cbm × 167)`). That is cm³ ÷ 5988, **not ÷ 6000**.
2. **Freight = max(minimum, rate × billed kg)**; the minimum applies to freight **before** surcharges. **Fuel + security are per kg of the billed weight** (identical rule text in all 10 sheets). No per-AWB fees, no other surcharges anywhere.
3. **All 10 sheets are EUR, valid 1–30 Nov 2026.** The portal can answer in another currency (`currency` + `fx_eur_per_usd` on the rate).
4. **Weight-break sets differ per airline** (250 vs 300 break, with or without 2000). Always also price at every higher break: billing as the next break is often cheaper (see §6).
5. **29 airlines, 22 truckers** on the carrier list. **15 airlines are on the portal** (2-letter codes), **10 only in the rate sheets**, **4 only by email** (ASU, KTM, PPT, TNR, ULN destinations: no sheet, no portal).
6. **114 portal lanes**, 107 distinct sheet lanes, **120 lanes in total**, all from 6 German origins (CGN DUS FRA HAM MUC STR) to 36 destinations. Every lane has 2–4 rate sources.
7. **Pickup zones** = 2-digit German postcode prefix → one of the 6 airports. The zone file has **no prices**: trucker prices only come from trucker bids by email.
8. **Gateway:** 32 OpenAI models allowed. Our OpenAI key **is stored** on the gateway since 13:30 UTC (it was `set: false` at the first snapshot, Julien stored it with PR #12).
9. **Board rules:** accuracy 45 · cost 40 · time 15 · humanity 10 · tracking 10. 14 teams, 0 rounds sent so far.
10. **The portal prices the weight you ask for, in that weight's bracket**: it does not do the next-break check for us.

## 1. Files in the kit

| File | Type | What it is |
|---|---|---|
| `carrier-list.csv` | CSV (name, kind, email, serves) | 29 airlines (serves = destination IATA codes) and 22 truckers (serves = 2-digit pickup zones); the only addresses besides customers, `ratedesk@` and `tracking@` we may mail |
| `pickup_zones.csv` | CSV (zone, area, airport) | 32 pickup zones (postcode prefixes) mapped to the 6 origin airports; no prices |
| `cobalt-skylift-tariff-2026-11.pdf` | PDF, 6 pages | Cobalt Skylift tariff, one vertical block per lane incl. fuel/security, blocks split across pages |
| `danube-wings-cargo-tariff-2026-11-p1.jpg` | JPG photo (skewed) | Danube Wings Cargo rates (page 1) |
| `danube-wings-cargo-tariff-2026-11-p2.jpg` | JPG photo (skewed) | Danube Wings Cargo surcharges (page 2) |
| `elbflug-air-freight-tariff-2026-11.xlsx` | Excel | Elbflug Air Freight, block per origin, numbers stored as text with comma decimals |
| `helix-air-freight-tariff-2026-11.pdf` | PDF, 1 page | Helix Air Freight, one row per lane, "EUR x.xx" cells, transit "D+n" |
| `kestrel-airways-tariff-2026-11.xlsx` | Excel | Kestrel Airways, block per origin, merged 2-row headers, fuel/security as columns |
| `orion-cargo-air-tariff-2026-11.pdf` | PDF, 4 pages | Orion Cargo Air, vertical block per lane, comma decimals, surcharges at the end |
| `quetzal-air-freight-tariff-2026-11.docx` | Word | Quetzal Air Freight, Word table, comma decimals, surcharges as text lines |
| `vega-skyfreight-tariff-2026-11.xlsx` | Excel | Vega Skyfreight, block per origin, destinations as "Lagos (LOS)", real numeric cells |
| `wayzata-air-cargo-tariff-2026-11.xlsx` | Excel | Wayzata Air Cargo, one table, lanes "CGN Cologne > DEL Delhi" |
| `yellowtail-air-freight-tariff-2026-11.txt` | Plain text | Yellowtail Air Freight, fixed-width table, breaks labelled -45/+45/+100/+250/... |

There is **no README, rules or instructions file in the kit**: the only rule text is the 4-line header repeated in every sheet (§3). Rules about scoring/process come from the API docs (§8) and the board (§9).

## 2. Carriers

### 2.1 Airlines (29)

Codes exist only for portal airlines (from `GET /v1/portal/ports`). The 10 sheet airlines and the 4 email-only airlines have no code in any kit file (`GET /v1/portal/brackets` returns 404 + the address to email for them, per the API docs).

| # | Airline | Code (portal) | Rate source | Email | Destinations served |
|---|---|---|---|---|---|
| 1 | Aurelia Air Cargo | AU | portal API | `aurelia-air-cargo@hackloop.mail` | CAI EZE LAX LIM MEL MIA NBO ORD RUH SCL SIN TLV YYZ |
| 2 | Borealis Freight Airways | BX | portal API | `borealis-freight-airways@hackloop.mail` | CAI DEL LIM NRT ORD PEK SCL SGN SYD YYZ |
| 3 | Cobalt Skylift | — | rate sheet (kit), email | `cobalt-skylift@hackloop.mail` | BOG BOM DEL EZE ICN JFK JNB LIM MEL MEX MIA RUH SGN SIN SYD TPE YYZ |
| 4 | Danube Wings Cargo | — | rate sheet (kit), email | `danube-wings-cargo@hackloop.mail` | DXB EZE JNB MEX SGN SYD TPE YYZ |
| 5 | Elbflug Air Freight | — | rate sheet (kit), email | `elbflug-air-freight@hackloop.mail` | BOG DFW DXB HKG LOS MEL MEX MIA ORD PVG SGN SIN SYD TLV |
| 6 | Fjordline Air Cargo | FQ | portal API | `fjordline-air-cargo@hackloop.mail` | ATL BOM DEL EZE GRU JFK JNB KUL LAX NBO SIN TLV |
| 7 | Gannet Airways | GN | portal API | `gannet-airways@hackloop.mail` | ICN LAX PEK TLV |
| 8 | Helix Air Freight | — | rate sheet (kit), email | `helix-air-freight@hackloop.mail` | HKG LAX LOS ORD PVG RUH SCL SGN SYD |
| 9 | Ibisair Cargo | IB | portal API | `ibisair-cargo@hackloop.mail` | ATL BKK BOG BOM DEL GRU HKG ICN JFK MEX MIA NBO ORD PEK SIN SYD YYZ |
| 10 | Juniper Cargo Lines | JP | portal API | `juniper-cargo-lines@hackloop.mail` | DEL EZE GRU MEL NBO RUH SCL SGN SYD TPE YYZ |
| 11 | Kestrel Airways | — | rate sheet (kit), email | `kestrel-airways@hackloop.mail` | BOM CAI DEL DFW GRU HKG KUL LAX MEL MEX MIA NRT PEK SIN |
| 12 | Lumen Air Cargo | LM | portal API | `lumen-air-cargo@hackloop.mail` | BOG BOM DFW DXB LOS MIA NRT PEK PVG RUH SGN YYZ |
| 13 | Meridian Freightways | MD | portal API | `meridian-freightways@hackloop.mail` | ATL CAI DEL DFW EZE HKG LAX MIA MNL NBO ORD PVG SYD TLV TPE |
| 14 | Nova Atlas Cargo | NV | portal API | `nova-atlas-cargo@hackloop.mail` | BKK EZE LIM MEL NRT ORD PVG SGN SIN SYD TPE |
| 15 | Orion Cargo Air | — | rate sheet (kit), email | `orion-cargo-air@hackloop.mail` | DXB GRU HKG KUL MIA MNL NBO ORD PEK SGN TLV |
| 16 | Polaris Air Logistics | PL | portal API | `polaris-air-logistics@hackloop.mail` | ATL BKK HKG ICN JFK JNB KUL LAX PEK SCL SGN SYD YYZ |
| 17 | Quetzal Air Freight | — | rate sheet (kit), email | `quetzal-air-freight@hackloop.mail` | BOM DFW DXB EZE HKG JFK LIM LOS RUH SCL |
| 18 | Riverbend Airlines Cargo | RV | portal API | `riverbend-airlines-cargo@hackloop.mail` | ATL BOG DFW DOH GRU MEX MIA RUH TLV YYZ |
| 19 | Solace Air Cargo | SL | portal API | `solace-air-cargo@hackloop.mail` | ATL BOG DEL GRU JFK MEL MEX MIA NRT SYD TLV TPE |
| 20 | Tamarind Airways | TM | portal API | `tamarind-airways@hackloop.mail` | BKK DXB EZE HKG JNB LOS MEX MIA MNL NBO PVG RUH SGN TLV YYZ |
| 21 | Ultraviolet Air Freight | UV | portal API | `ultraviolet-air-freight@hackloop.mail` | BOM DEL DFW DOH EZE GRU JFK LAX MEX MNL NBO RUH SCL SIN SYD TLV YYZ |
| 22 | Vega Skyfreight | — | rate sheet (kit), email | `vega-skyfreight@hackloop.mail` | DEL DFW KUL LIM LOS MIA MNL NBO ORD PEK SYD YYZ |
| 23 | Wayzata Air Cargo | — | rate sheet (kit), email | `wayzata-air-cargo@hackloop.mail` | ATL BOG CAI DEL DOH DXB EZE HKG ICN JFK LAX LIM MEX MIA NBO NRT PEK SCL SGN TLV |
| 24 | Xenon Cargo Airlines | XC | portal API | `xenon-cargo-airlines@hackloop.mail` | BOG BOM LIM MEX MIA NRT ORD PVG SCL |
| 25 | Yellowtail Air Freight | — | rate sheet (kit), email | `yellowtail-air-freight@hackloop.mail` | BKK BOG DFW JFK JNB LAX LIM MEL MEX MNL NBO ORD SGN SYD |
| 26 | Zephyr Steppe Cargo | — | email only (no sheet, not on portal) | `zephyr-steppe-cargo@hackloop.mail` | ASU KTM PPT TNR ULN |
| 27 | Himalaya Bridge Air | — | email only (no sheet, not on portal) | `himalaya-bridge-air@hackloop.mail` | ASU KTM TNR ULN |
| 28 | Lagoon Isles Airways | — | email only (no sheet, not on portal) | `lagoon-isles-airways@hackloop.mail` | ASU PPT TNR ULN |
| 29 | Pampero Air Cargo | — | email only (no sheet, not on portal) | `pampero-air-cargo@hackloop.mail` | ASU KTM PPT TNR ULN |

### 2.2 Truckers (22)

| # | Trucker | Email | Pickup zones served | Airports reached (via zone map) |
|---|---|---|---|---|
| 1 | Rheinufer Spedition | `rheinufer-spedition@hackloop.mail` | 20 40 42 47 64 70 73 | DUS FRA HAM STR |
| 2 | Maintal Transport Logistik | `maintal-transport-logistik@hackloop.mail` | 21 24 45 51 65 84 86 | CGN DUS FRA HAM MUC |
| 3 | Alpenblick Logistik | `alpenblick-logistik@hackloop.mail` | 24 64 72 81 | FRA HAM MUC STR |
| 4 | Hansekogge Trucking | `hansekogge-trucking@hackloop.mail` | 20 24 40 50 61 72 73 | CGN DUS FRA HAM STR |
| 5 | Neckarstrom Kurier | `neckarstrom-kurier@hackloop.mail` | 24 55 65 73 80 81 85 86 93 | FRA HAM MUC STR |
| 6 | Ruhrpott Express | `ruhrpott-express@hackloop.mail` | 22 41 50 53 80 85 | CGN DUS HAM MUC |
| 7 | Taunusfracht | `taunusfracht@hackloop.mail` | 22 45 60 | DUS FRA HAM |
| 8 | Isarwelle Spedition | `isarwelle-spedition@hackloop.mail` | 60 70 80 84 93 | FRA MUC STR |
| 9 | Elbkante Logistik | `elbkante-logistik@hackloop.mail` | 20 35 47 51 55 84 85 93 | CGN DUS FRA HAM MUC |
| 10 | Schwabenbote Transporte | `schwabenbote-transporte@hackloop.mail` | 28 40 42 44 55 | DUS FRA HAM |
| 11 | Domblick Kurierdienst | `domblick-kurierdienst@hackloop.mail` | 21 36 40 45 47 60 63 73 85 | DUS FRA HAM MUC STR |
| 12 | Westfalenroute | `westfalenroute@hackloop.mail` | 42 51 60 61 63 | CGN DUS FRA |
| 13 | Odenwald Cargo | `odenwald-cargo@hackloop.mail` | 21 41 85 | DUS HAM MUC |
| 14 | Spessart Spedition | `spessart-spedition@hackloop.mail` | 21 28 42 53 61 70 73 | CGN DUS FRA HAM STR |
| 15 | Bodenseefracht | `bodenseefracht@hackloop.mail` | 36 45 51 60 61 80 | CGN DUS FRA MUC |
| 16 | Nordlicht Haulage | `nordlicht-haulage@hackloop.mail` | 20 22 61 70 80 | FRA HAM MUC STR |
| 17 | Waldrand Transporte | `waldrand-transporte@hackloop.mail` | 21 28 55 | FRA HAM |
| 18 | Kranich Kurier | `kranich-kurier@hackloop.mail` | 22 50 64 65 71 81 | CGN FRA HAM MUC STR |
| 19 | Flinkwagen Logistik | `flinkwagen-logistik@hackloop.mail` | 24 44 65 71 84 93 | DUS FRA HAM MUC STR |
| 20 | Grautal Trucking | `grautal-trucking@hackloop.mail` | 45 | DUS |
| 21 | Sternmeile Logistik | `sternmeile-logistik@hackloop.mail` | 20 35 50 53 81 86 | CGN FRA HAM MUC |
| 22 | Vogelsberg Haulage | `vogelsberg-haulage@hackloop.mail` | 36 41 44 47 55 | DUS FRA |

Trucker zones that are not in `pickup_zones.csv`: none.

## 3. Pickup zones (32)

The zone is the first two digits of the German postcode. Each zone maps to exactly one origin airport. Note the non-obvious ones: Bremen (28) and Kiel (24) → HAM; Mainz (55), Giessen (35), Fulda (36) → FRA; Augsburg (86), Regensburg (93), Ingolstadt (85), Landshut (84) → MUC; Dortmund (44), Essen (45), Duisburg (47), Wuppertal (42) → DUS; Bonn (53) → CGN.

| Zone | Area | Airport | Truckers serving it |
|---|---|---|---|
| 50 | Cologne | CGN | 4: Hansekogge Trucking, Ruhrpott Express, Kranich Kurier, Sternmeile Logistik |
| 51 | Bergisch Gladbach | CGN | 4: Maintal Transport Logistik, Elbkante Logistik, Westfalenroute, Bodenseefracht |
| 53 | Bonn | CGN | 3: Ruhrpott Express, Spessart Spedition, Sternmeile Logistik |
| 40 | Duesseldorf | DUS | 4: Rheinufer Spedition, Hansekogge Trucking, Schwabenbote Transporte, Domblick Kurierdienst |
| 41 | Moenchengladbach | DUS | 3: Ruhrpott Express, Odenwald Cargo, Vogelsberg Haulage |
| 42 | Wuppertal | DUS | 4: Rheinufer Spedition, Schwabenbote Transporte, Westfalenroute, Spessart Spedition |
| 44 | Dortmund | DUS | 3: Schwabenbote Transporte, Flinkwagen Logistik, Vogelsberg Haulage |
| 45 | Essen | DUS | 5: Maintal Transport Logistik, Taunusfracht, Domblick Kurierdienst, Bodenseefracht, Grautal Trucking |
| 47 | Duisburg | DUS | 4: Rheinufer Spedition, Elbkante Logistik, Domblick Kurierdienst, Vogelsberg Haulage |
| 35 | Giessen | FRA | 2: Elbkante Logistik, Sternmeile Logistik |
| 36 | Fulda | FRA | 3: Domblick Kurierdienst, Bodenseefracht, Vogelsberg Haulage |
| 55 | Mainz | FRA | 5: Neckarstrom Kurier, Elbkante Logistik, Schwabenbote Transporte, Waldrand Transporte, Vogelsberg Haulage |
| 60 | Frankfurt am Main | FRA | 5: Taunusfracht, Isarwelle Spedition, Domblick Kurierdienst, Westfalenroute, Bodenseefracht |
| 61 | Bad Homburg | FRA | 5: Hansekogge Trucking, Westfalenroute, Spessart Spedition, Bodenseefracht, Nordlicht Haulage |
| 63 | Offenbach | FRA | 2: Domblick Kurierdienst, Westfalenroute |
| 64 | Darmstadt | FRA | 3: Rheinufer Spedition, Alpenblick Logistik, Kranich Kurier |
| 65 | Wiesbaden | FRA | 4: Maintal Transport Logistik, Neckarstrom Kurier, Kranich Kurier, Flinkwagen Logistik |
| 20 | Hamburg | HAM | 5: Rheinufer Spedition, Hansekogge Trucking, Elbkante Logistik, Nordlicht Haulage, Sternmeile Logistik |
| 21 | Lueneburg | HAM | 5: Maintal Transport Logistik, Domblick Kurierdienst, Odenwald Cargo, Spessart Spedition, Waldrand Transporte |
| 22 | Hamburg North | HAM | 4: Ruhrpott Express, Taunusfracht, Nordlicht Haulage, Kranich Kurier |
| 24 | Kiel | HAM | 5: Maintal Transport Logistik, Alpenblick Logistik, Hansekogge Trucking, Neckarstrom Kurier, Flinkwagen Logistik |
| 28 | Bremen | HAM | 3: Schwabenbote Transporte, Spessart Spedition, Waldrand Transporte |
| 80 | Munich | MUC | 5: Neckarstrom Kurier, Ruhrpott Express, Isarwelle Spedition, Bodenseefracht, Nordlicht Haulage |
| 81 | Munich South | MUC | 4: Alpenblick Logistik, Neckarstrom Kurier, Kranich Kurier, Sternmeile Logistik |
| 84 | Landshut | MUC | 4: Maintal Transport Logistik, Isarwelle Spedition, Elbkante Logistik, Flinkwagen Logistik |
| 85 | Ingolstadt | MUC | 5: Neckarstrom Kurier, Ruhrpott Express, Elbkante Logistik, Domblick Kurierdienst, Odenwald Cargo |
| 86 | Augsburg | MUC | 3: Maintal Transport Logistik, Neckarstrom Kurier, Sternmeile Logistik |
| 93 | Regensburg | MUC | 4: Neckarstrom Kurier, Isarwelle Spedition, Elbkante Logistik, Flinkwagen Logistik |
| 70 | Stuttgart | STR | 4: Rheinufer Spedition, Isarwelle Spedition, Spessart Spedition, Nordlicht Haulage |
| 71 | Boeblingen | STR | 2: Kranich Kurier, Flinkwagen Logistik |
| 72 | Tuebingen | STR | 2: Alpenblick Logistik, Hansekogge Trucking |
| 73 | Esslingen | STR | 5: Rheinufer Spedition, Hansekogge Trucking, Neckarstrom Kurier, Domblick Kurierdienst, Spessart Spedition |

## 4. Rate sheets

### 4.1 Rules text (identical in all 10 sheets, verbatim meaning)

- All rates are per kg of chargeable weight, in EUR.
- Chargeable weight is the higher of actual weight and volume weight (1 cbm = 167 kg).
- Fuel and security surcharges are charged per kg of the weight the freight is billed on.
- The minimum charge applies to the freight before surcharges.
- A section titled "Surcharges per kg of billed weight" (or columns/rows inside each lane block for Kestrel and Cobalt) gives fuel and security per lane.

No footnotes, no per-AWB/handling/screening fees, no commodity or DG rules, no rounding rule, no validity per lane.

### 4.2 Overview

| Airline | Lanes | Origins | Weight breaks (kg) | Minimum (EUR) | Fuel/kg | Security/kg | Transit (d) | Validity as printed |
|---|---|---|---|---|---|---|---|---|
| Yellowtail Air Freight | 15 | CGN×1 DUS×1 FRA×5 HAM×3 MUC×2 STR×3 | <45 / 45+ / 100+ / 250+ / 500+ / 1000+ / 2000+ | 61.00–137.80 | 0.66–1.43 | 0.11–0.27 | 2–7 | 01.11.2026 – 30.11.2026 |
| Danube Wings Cargo | 9 | CGN×1 DUS×3 FRA×2 MUC×2 STR×1 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ | 62.00–138.86 | 0.69–1.15 | 0.11–0.24 | 2–7 | 1 November 2026 – 30 November 2026 |
| Cobalt Skylift | 21 | CGN×3 DUS×4 FRA×5 HAM×2 MUC×6 STR×1 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ / 2000+ | 58.00–138.00 | 0.62–1.34 | 0.10–0.25 | 2–6 | 01/11/2026 – 30/11/2026 |
| Helix Air Freight | 12 | CGN×2 DUS×1 FRA×3 HAM×1 MUC×3 STR×2 | <45 / 45+ / 100+ / 250+ / 500+ / 1000+ / 2000+ | 64.00–140.00 | 0.60–1.40 | 0.11–0.25 | 1–6 | 01.11.2026 – 30.11.2026 |
| Orion Cargo Air | 14 | CGN×2 FRA×5 HAM×1 MUC×3 STR×3 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ | 70.00–139.00 | 0.61–1.20 | 0.10–0.27 | 2–5 | 2026-11-01 – 2026-11-30 |
| Quetzal Air Freight | 11 | CGN×2 DUS×1 FRA×3 HAM×1 MUC×3 STR×1 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ / 2000+ | 70.00–139.00 | 0.56–1.28 | 0.11–0.25 | 1–5 | 2026-11-01 – 2026-11-30 |
| Elbflug Air Freight | 19 | CGN×1 DUS×2 FRA×8 HAM×4 MUC×2 STR×2 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ | 65.00–140.98 | 0.66–1.34 | 0.10–0.25 | 1–7 | Excel date cells (dd/mm/yyyy) 01/11/2026 – 30/11/2026 |
| Kestrel Airways | 18 | CGN×1 DUS×3 FRA×6 HAM×2 MUC×5 STR×1 | <45 / 45+ / 100+ / 250+ / 500+ / 1000+ / 2000+ | 56.00–137.80 | 0.62–1.31 | 0.10–0.27 | 1–6 | Excel date cells (dd/mm/yyyy) 01/11/2026 – 30/11/2026 |
| Vega Skyfreight | 13 | CGN×1 DUS×2 FRA×1 HAM×4 MUC×3 STR×2 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ / 2000+ | 56.00–144.16 | 0.65–1.37 | 0.10–0.25 | 1–6 | text '2026-11-01' – '2026-11-30' |
| Wayzata Air Cargo | 26 | CGN×4 DUS×3 FRA×7 HAM×3 MUC×8 STR×1 | <45 / 45+ / 100+ / 300+ / 500+ / 1000+ | 55.00–144.16 | 0.56–1.31 | 0.11–0.26 | 1–6 | Excel date cells (dd/mm/yyyy) 01/11/2026 – 30/11/2026 |

"<45" is the first bracket (labelled "from 0 kg", "0 kg+" or "-45" depending on the sheet). Volume divisor is 1 cbm = 167 kg in every sheet. Currency is EUR in every sheet.

### 4.3 Format per sheet (what the parser must handle)

| Airline | Format details |
|---|---|
| Yellowtail Air Freight | `.txt`, fixed-width; values "EUR 5.92"; breaks "-45 +45 +100 +250 +500 +1000 +2000"; transit integer; surcharges as "CGN-SYD: fuel EUR 0.76 per kg, security EUR 0.21 per kg"; dates `01.11.2026` |
| Danube Wings Cargo | 2 photographed, slightly rotated JPGs → needs vision/OCR (tesseract reads it but garbles ~5 cells, e.g. `1,57`→`alfsy/`; the STR-SGN row was dropped by OCR). p1 rates ("from 0 kg … from 1000 kg", no 2000), p2 fuel/security; comma decimals; transit "N days"; dates "1 November 2026" |
| Cobalt Skylift | PDF with text layer; one vertical block per lane: heading "CGN Cologne > EZE Buenos Aires", then Transit, Minimum, "from N kg" ×7, Fuel, Security; blocks break across pages; dot decimals; dates `01/11/2026` |
| Helix Air Freight | PDF table; lanes "Cologne (CGN) to Lagos (LOS)"; transit "D+4"; "EUR x.xx"; breaks include **250** (not 300); surcharges listed below |
| Orion Cargo Air | PDF vertical blocks "CGN-MIA" / Transit "2 days" / Minimum / "from N kg" ×6 (no 2000); comma decimals; blocks split across pages; surcharges at the end |
| Quetzal Air Freight | `.docx` table; breaks "0 kg+ … 2000 kg+"; comma decimals; surcharges as text paragraphs "CGN-DFW: fuel 1,14 per kg, security 0,24 per kg" |
| Elbflug Air Freight | `.xlsx`; block per origin ("Origin: CGN"), rows = destination code; **numbers are text cells with comma decimals** (`'108,00'`); no 2000 break; dates are real Excel dates |
| Kestrel Airways | `.xlsx`; block per origin; merged header "Rate per kg by weight break" + "-45/+45/+100/+250/+500/+1000/+2000"; transit **"D+4"**; fuel/security in columns K/L of each row; numbers are text with comma decimals |
| Vega Skyfreight | `.xlsx`; block per origin "Origin: Cologne (CGN)"; rows "Lagos (LOS)"; real numeric cells; breaks "-45 … +2000" with 300; dates as text "2026-11-01"; surcharges "Cologne (CGN) to Lagos (LOS): fuel 1.29 per kg, …" |
| Wayzata Air Cargo | `.xlsx`; single table, lanes "CGN Cologne > DEL Delhi"; transit "2 days"/"1 day"; real numeric cells; breaks "-45 … +1000" (no 2000); surcharges as text lines |

### 4.4 Full rate tables

Columns are weight breaks in kg ("<45" = first bracket). A bracket runs from its break up to the next break. Fuel and security are EUR per kg of billed weight.

#### Yellowtail Air Freight: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 250+ | 500+ | 1000+ | 2000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CGN-SYD | 5 | 75.00 | 5.92 | 5.03 | 3.87 | 3.02 | 2.33 | 1.86 | 1.54 | 0.76 | 0.21 |
| DUS-JFK | 5 | 100.00 | 3.96 | 3.21 | 2.82 | 2.34 | 1.83 | 1.50 | 1.25 | 1.09 | 0.13 |
| FRA-BKK | 2 | 91.00 | 4.19 | 3.40 | 2.86 | 2.26 | 1.90 | 1.58 | 1.26 | 1.05 | 0.27 |
| FRA-DFW | 2 | 109.00 | 3.76 | 2.78 | 2.42 | 2.20 | 1.69 | 1.52 | 1.22 | 0.85 | 0.25 |
| FRA-LIM | 5 | 72.00 | 5.09 | 4.12 | 3.63 | 2.72 | 2.20 | 1.58 | 1.37 | 1.10 | 0.19 |
| FRA-NBO | 7 | 91.00 | 4.30 | 3.78 | 2.87 | 2.18 | 1.98 | 1.54 | 1.19 | 0.94 | 0.16 |
| FRA-ORD | 4 | 110.00 | 3.73 | 3.32 | 2.42 | 1.82 | 1.64 | 1.46 | 1.14 | 0.66 | 0.11 |
| HAM-BOG | 2 | 127.20 | 4.62 | 4.06 | 3.53 | 3.53 | 2.44 | 1.76 | 1.29 | 1.43 | 0.23 |
| HAM-MEX | 3 | 81.00 | 3.28 | 2.49 | 2.17 | 1.67 | 1.50 | 1.38 | 1.10 | 0.68 | 0.21 |
| HAM-SGN | 6 | 68.00 | 4.45 | 3.69 | 2.77 | 2.47 | 1.80 | 1.46 | 1.28 | 0.91 | 0.11 |
| MUC-JNB | 4 | 117.00 | 4.02 | 3.10 | 2.54 | 2.33 | 1.48 | 1.30 | 1.30 | 0.91 | 0.26 |
| MUC-LAX | 5 | 82.00 | 3.12 | 2.28 | 1.73 | 1.40 | 1.08 | 0.98 | 0.83 | 1.17 | 0.14 |
| STR-LAX | 2 | 137.80 | 3.81 | 2.78 | 2.37 | 2.37 | 1.55 | 1.25 | 1.25 | 1.06 | 0.27 |
| STR-MEL | 5 | 102.00 | 6.48 | 5.83 | 5.01 | 4.36 | 3.49 | 2.97 | 2.38 | 1.16 | 0.24 |
| STR-MNL | 5 | 61.00 | 3.37 | 2.76 | 2.35 | 1.76 | 1.60 | 1.44 | 1.17 | 1.32 | 0.23 |

#### Danube Wings Cargo: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|
| CGN-SYD | 4 | 134.00 | 6.28 | 5.34 | 4.28 | 3.89 | 3.27 | 2.84 | 1.13 | 0.23 |
| DUS-MEX | 5 | 101.00 | 3.02 | 2.36 | 1.89 | 1.57 | 1.32 | 1.00 | 0.74 | 0.24 |
| DUS-SYD | 5 | 110.00 | 5.78 | 4.45 | 3.92 | 2.90 | 2.20 | 1.89 | 0.69 | 0.16 |
| DUS-YYZ | 4 | 62.00 | 3.08 | 2.62 | 2.07 | 1.61 | 1.22 | 0.96 | 0.88 | 0.21 |
| FRA-DXB | 2 | 138.86 | 2.90 | 2.23 | 2.05 | 1.66 | 1.45 | 1.33 | 1.12 | 0.22 |
| FRA-EZE | 2 | 126.00 | 4.57 | 3.34 | 2.74 | 2.52 | 1.92 | 1.48 | 1.06 | 0.21 |
| MUC-JNB | 7 | 105.00 | 3.74 | 2.81 | 2.19 | 1.62 | 1.39 | 1.22 | 0.85 | 0.24 |
| MUC-TPE | 5 | 69.00 | 4.10 | 3.73 | 3.21 | 2.57 | 2.36 | 2.03 | 1.15 | 0.21 |
| STR-SGN | 5 | 83.00 | 4.63 | 4.21 | 3.45 | 2.93 | 2.40 | 2.18 | 1.09 | 0.11 |

#### Cobalt Skylift: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | 2000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CGN-EZE | 5 | 79.00 | 5.41 | 4.17 | 3.21 | 2.89 | 2.54 | 2.06 | 1.67 | 0.70 | 0.20 |
| CGN-SGN | 4 | 73.00 | 4.22 | 3.67 | 3.19 | 2.49 | 1.84 | 1.51 | 1.27 | 1.01 | 0.23 |
| CGN-SIN | 4 | 102.00 | 4.70 | 3.48 | 2.61 | 1.91 | 1.74 | 1.46 | 1.27 | 1.16 | 0.21 |
| DUS-BOM | 5 | 115.00 | 3.42 | 2.80 | 2.24 | 1.79 | 1.58 | 1.17 | 0.92 | 1.16 | 0.20 |
| DUS-DEL | 4 | 68.00 | 4.18 | 3.30 | 2.87 | 2.44 | 2.20 | 1.63 | 1.34 | 0.62 | 0.22 |
| DUS-JFK | 4 | 78.00 | 3.13 | 2.38 | 2.17 | 1.84 | 1.36 | 1.22 | 0.93 | 0.80 | 0.23 |
| DUS-SYD | 4 | 68.00 | 6.53 | 4.90 | 3.63 | 2.61 | 2.24 | 2.02 | 1.47 | 0.85 | 0.11 |
| FRA-BOG | 4 | 83.74 | 5.10 | 4.10 | 3.24 | 2.92 | 2.25 | 1.76 | 1.46 | 1.34 | 0.17 |
| FRA-ICN | 6 | 58.00 | 3.23 | 2.55 | 1.84 | 1.36 | 1.17 | 1.01 | 0.85 | 1.21 | 0.11 |
| FRA-JNB | 4 | 118.72 | 5.33 | 4.37 | 3.36 | 2.99 | 2.45 | 2.25 | 1.71 | 1.30 | 0.23 |
| FRA-SYD | 6 | 124.00 | 5.36 | 4.45 | 4.05 | 3.04 | 2.71 | 2.44 | 2.15 | 0.65 | 0.18 |
| FRA-TPE | 3 | 71.00 | 4.33 | 3.46 | 2.56 | 1.95 | 1.72 | 1.55 | 1.30 | 1.12 | 0.10 |
| HAM-BOG | 3 | 77.00 | 4.63 | 3.94 | 3.03 | 2.39 | 1.82 | 1.57 | 1.22 | 1.04 | 0.25 |
| HAM-RUH | 3 | 114.00 | 3.32 | 2.62 | 2.12 | 1.55 | 1.26 | 1.15 | 1.04 | 0.92 | 0.21 |
| MUC-BOG | 4 | 94.34 | 5.11 | 3.74 | 3.03 | 2.63 | 2.40 | 2.00 | 1.84 | 1.28 | 0.23 |
| MUC-LIM | 6 | 137.00 | 4.49 | 3.23 | 2.49 | 2.17 | 1.84 | 1.62 | 1.31 | 0.70 | 0.22 |
| MUC-MEL | 3 | 138.00 | 6.24 | 5.49 | 4.83 | 4.20 | 3.49 | 2.69 | 2.37 | 0.99 | 0.25 |
| MUC-MEX | 3 | 63.00 | 3.98 | 2.95 | 2.36 | 1.94 | 1.63 | 1.35 | 1.04 | 0.73 | 0.16 |
| MUC-MIA | 2 | 134.00 | 4.00 | 3.37 | 2.62 | 2.23 | 2.05 | 1.61 | 1.61 | 0.84 | 0.18 |
| MUC-YYZ | 3 | 123.00 | 3.93 | 3.22 | 2.32 | 2.06 | 1.90 | 1.43 | 1.13 | 1.29 | 0.15 |
| STR-YYZ | 4 | 72.00 | 3.08 | 2.22 | 1.60 | 1.46 | 1.23 | 1.07 | 0.77 | 0.71 | 0.17 |

#### Helix Air Freight: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 250+ | 500+ | 1000+ | 2000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CGN-LOS | 4 | 76.00 | 4.62 | 3.83 | 3.49 | 2.65 | 1.93 | 1.70 | 1.29 | 1.04 | 0.12 |
| CGN-SYD | 6 | 124.00 | 5.52 | 4.91 | 3.98 | 3.62 | 2.93 | 2.67 | 2.22 | 0.98 | 0.11 |
| DUS-RUH | 3 | 64.00 | 3.37 | 2.93 | 2.64 | 2.09 | 1.88 | 1.73 | 1.37 | 0.60 | 0.13 |
| FRA-LAX | 1 | 112.00 | 3.33 | 2.73 | 2.24 | 2.24 | 1.62 | 1.25 | 1.25 | 1.40 | 0.21 |
| FRA-PVG | 2 | 102.00 | 4.66 | 3.45 | 3.03 | 2.64 | 2.40 | 2.17 | 1.82 | 0.85 | 0.23 |
| FRA-SCL | 3 | 92.00 | 4.68 | 3.84 | 3.11 | 2.24 | 1.86 | 1.66 | 1.31 | 0.84 | 0.23 |
| HAM-HKG | 2 | 130.38 | 4.16 | 3.62 | 2.61 | 2.52 | 1.90 | 1.69 | 1.69 | 1.29 | 0.25 |
| MUC-HKG | 5 | 105.00 | 3.68 | 2.94 | 2.68 | 2.44 | 2.22 | 2.02 | 1.58 | 0.84 | 0.21 |
| MUC-PVG | 5 | 140.00 | 3.54 | 2.58 | 2.17 | 1.82 | 1.64 | 1.48 | 1.20 | 0.86 | 0.13 |
| MUC-SGN | 6 | 65.00 | 4.56 | 4.10 | 3.57 | 3.07 | 2.49 | 1.87 | 1.55 | 1.32 | 0.24 |
| STR-ORD | 3 | 133.00 | 3.84 | 3.11 | 2.86 | 2.37 | 2.16 | 1.56 | 1.36 | 0.82 | 0.23 |
| STR-PVG | 4 | 81.00 | 3.79 | 3.34 | 2.74 | 2.52 | 1.92 | 1.67 | 1.50 | 0.74 | 0.20 |

#### Orion Cargo Air: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|
| CGN-MIA | 2 | 78.00 | 2.91 | 2.12 | 1.61 | 1.26 | 1.10 | 0.84 | 1.11 | 0.23 |
| CGN-TLV | 2 | 73.00 | 3.25 | 2.54 | 1.83 | 1.68 | 1.55 | 1.19 | 0.61 | 0.10 |
| FRA-KUL | 4 | 72.00 | 3.04 | 2.40 | 1.97 | 1.67 | 1.29 | 1.10 | 0.69 | 0.17 |
| FRA-NBO | 4 | 96.46 | 4.56 | 4.01 | 3.05 | 2.37 | 2.10 | 1.64 | 1.00 | 0.17 |
| FRA-ORD | 2 | 114.00 | 3.46 | 3.15 | 2.52 | 2.02 | 1.47 | 1.07 | 0.97 | 0.13 |
| FRA-PEK | 4 | 139.00 | 4.05 | 3.40 | 2.65 | 1.99 | 1.57 | 1.43 | 0.87 | 0.15 |
| FRA-SGN | 5 | 77.00 | 2.92 | 2.19 | 1.97 | 1.58 | 1.33 | 1.06 | 1.19 | 0.13 |
| HAM-DXB | 4 | 91.00 | 3.37 | 2.49 | 2.07 | 1.76 | 1.50 | 1.14 | 1.01 | 0.17 |
| MUC-GRU | 4 | 103.00 | 5.26 | 4.47 | 3.58 | 3.11 | 2.49 | 2.12 | 1.02 | 0.11 |
| MUC-HKG | 3 | 111.30 | 4.31 | 3.84 | 3.46 | 3.01 | 2.50 | 2.15 | 0.96 | 0.23 |
| MUC-NBO | 3 | 132.00 | 5.25 | 4.68 | 4.08 | 3.26 | 2.77 | 2.19 | 1.20 | 0.27 |
| STR-MNL | 4 | 120.00 | 3.72 | 3.27 | 2.58 | 2.09 | 1.63 | 1.43 | 1.03 | 0.14 |
| STR-PEK | 5 | 70.00 | 3.36 | 2.76 | 2.37 | 1.85 | 1.48 | 1.08 | 0.71 | 0.19 |
| STR-TLV | 4 | 118.00 | 3.43 | 2.78 | 2.22 | 1.86 | 1.34 | 0.98 | 0.94 | 0.23 |

#### Quetzal Air Freight: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | 2000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CGN-DFW | 2 | 76.00 | 3.10 | 2.79 | 2.18 | 1.61 | 1.19 | 0.89 | 0.75 | 1.14 | 0.24 |
| CGN-LOS | 4 | 139.00 | 5.31 | 4.19 | 3.23 | 2.84 | 2.13 | 1.83 | 1.68 | 1.16 | 0.22 |
| DUS-HKG | 4 | 108.00 | 4.68 | 3.93 | 3.18 | 2.58 | 2.04 | 1.53 | 1.41 | 1.26 | 0.13 |
| FRA-BOM | 3 | 127.00 | 3.44 | 2.75 | 2.20 | 1.98 | 1.82 | 1.60 | 1.22 | 0.56 | 0.11 |
| FRA-LIM | 5 | 106.00 | 4.45 | 3.65 | 2.88 | 2.33 | 1.89 | 1.55 | 1.40 | 1.26 | 0.18 |
| FRA-RUH | 2 | 129.00 | 3.17 | 2.63 | 2.26 | 1.79 | 1.43 | 1.26 | 1.26 | 0.95 | 0.18 |
| HAM-JFK | 1 | 116.00 | 3.43 | 2.81 | 2.31 | 2.05 | 1.58 | 1.17 | 1.03 | 0.83 | 0.23 |
| MUC-DXB | 2 | 97.00 | 3.09 | 2.53 | 2.20 | 1.94 | 1.71 | 1.47 | 1.26 | 1.01 | 0.25 |
| MUC-EZE | 5 | 132.00 | 5.01 | 4.51 | 3.88 | 2.79 | 2.48 | 1.96 | 1.69 | 1.28 | 0.24 |
| MUC-RUH | 3 | 70.00 | 3.05 | 2.41 | 2.22 | 2.04 | 1.59 | 1.16 | 0.88 | 0.74 | 0.14 |
| STR-SCL | 2 | 111.30 | 4.82 | 4.14 | 3.64 | 3.16 | 2.75 | 2.39 | 2.39 | 1.23 | 0.24 |

#### Elbflug Air Freight: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|
| CGN-LOS | 5 | 108.00 | 3.87 | 3.06 | 2.63 | 2.18 | 1.94 | 1.59 | 1.21 | 0.10 |
| DUS-HKG | 4 | 67.00 | 3.10 | 2.29 | 1.65 | 1.32 | 1.19 | 0.96 | 0.76 | 0.12 |
| DUS-TLV | 1 | 85.86 | 3.52 | 2.89 | 2.49 | 1.87 | 1.35 | 1.04 | 1.34 | 0.14 |
| FRA-BOG | 7 | 65.00 | 4.69 | 3.94 | 3.51 | 2.56 | 2.28 | 1.85 | 0.84 | 0.13 |
| FRA-DFW | 3 | 108.00 | 2.79 | 2.01 | 1.57 | 1.19 | 0.92 | 0.84 | 0.74 | 0.14 |
| FRA-DXB | 3 | 131.00 | 2.73 | 2.10 | 1.93 | 1.56 | 1.36 | 1.25 | 0.91 | 0.20 |
| FRA-HKG | 4 | 75.00 | 3.32 | 2.39 | 1.91 | 1.51 | 1.22 | 0.98 | 0.84 | 0.22 |
| FRA-MEL | 7 | 134.00 | 4.99 | 3.79 | 3.26 | 2.71 | 2.09 | 1.76 | 1.22 | 0.14 |
| FRA-MIA | 5 | 91.00 | 3.84 | 3.11 | 2.46 | 2.14 | 1.90 | 1.52 | 1.29 | 0.25 |
| FRA-SGN | 3 | 115.00 | 4.07 | 3.70 | 3.15 | 2.71 | 2.20 | 1.74 | 0.77 | 0.14 |
| FRA-SIN | 3 | 72.00 | 4.07 | 3.34 | 2.54 | 2.24 | 2.06 | 1.65 | 0.85 | 0.24 |
| HAM-DFW | 4 | 79.00 | 3.10 | 2.48 | 2.03 | 1.46 | 1.27 | 0.97 | 1.29 | 0.13 |
| HAM-DXB | 2 | 114.00 | 3.58 | 2.64 | 2.31 | 1.87 | 1.59 | 1.44 | 1.09 | 0.21 |
| HAM-MEX | 3 | 117.00 | 2.86 | 2.57 | 1.98 | 1.43 | 1.27 | 1.12 | 1.34 | 0.25 |
| HAM-TLV | 3 | 128.00 | 2.72 | 2.48 | 2.21 | 1.90 | 1.60 | 1.22 | 0.66 | 0.22 |
| MUC-BOG | 6 | 75.00 | 4.38 | 3.15 | 2.74 | 2.22 | 1.95 | 1.79 | 0.89 | 0.14 |
| MUC-SYD | 6 | 105.00 | 5.52 | 4.42 | 3.54 | 3.12 | 2.43 | 1.87 | 0.77 | 0.22 |
| STR-ORD | 2 | 140.98 | 4.08 | 3.30 | 3.04 | 2.52 | 2.29 | 1.66 | 0.87 | 0.25 |
| STR-PVG | 4 | 112.00 | 4.72 | 3.45 | 2.76 | 2.04 | 1.61 | 1.37 | 1.24 | 0.10 |

#### Kestrel Airways: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 250+ | 500+ | 1000+ | 2000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CGN-MIA | 4 | 76.00 | 3.05 | 2.35 | 1.72 | 1.38 | 1.16 | 0.97 | 0.85 | 0.69 | 0.24 |
| DUS-DFW | 1 | 119.00 | 4.06 | 3.45 | 3.11 | 2.72 | 1.86 | 1.56 | 1.47 | 1.29 | 0.21 |
| DUS-KUL | 5 | 56.00 | 4.15 | 3.11 | 2.74 | 2.52 | 1.92 | 1.73 | 1.51 | 1.04 | 0.15 |
| DUS-NRT | 2 | 113.42 | 4.39 | 4.04 | 3.31 | 2.78 | 1.91 | 1.43 | 1.17 | 1.31 | 0.21 |
| FRA-BOM | 2 | 134.62 | 4.25 | 3.23 | 2.34 | 2.34 | 1.93 | 1.70 | 1.30 | 0.81 | 0.13 |
| FRA-CAI | 3 | 118.00 | 4.64 | 3.62 | 2.64 | 1.90 | 1.52 | 1.19 | 1.09 | 0.88 | 0.22 |
| FRA-DEL | 3 | 97.52 | 3.20 | 2.82 | 2.48 | 2.03 | 1.75 | 1.45 | 1.32 | 1.27 | 0.27 |
| FRA-MEX | 4 | 79.00 | 3.11 | 2.61 | 2.19 | 1.95 | 1.44 | 1.15 | 0.94 | 1.15 | 0.17 |
| FRA-MIA | 2 | 137.80 | 3.18 | 2.52 | 2.04 | 1.93 | 1.55 | 1.19 | 1.02 | 0.94 | 0.21 |
| FRA-NRT | 4 | 116.00 | 3.50 | 2.66 | 2.34 | 2.01 | 1.61 | 1.37 | 1.14 | 0.89 | 0.14 |
| HAM-HKG | 4 | 73.00 | 3.18 | 2.70 | 2.48 | 1.93 | 1.66 | 1.20 | 1.06 | 0.63 | 0.15 |
| HAM-PEK | 3 | 133.56 | 4.47 | 3.70 | 3.26 | 3.26 | 2.34 | 1.75 | 1.30 | 0.96 | 0.21 |
| MUC-GRU | 5 | 127.00 | 4.09 | 3.39 | 2.92 | 2.69 | 2.10 | 1.87 | 1.53 | 0.62 | 0.18 |
| MUC-LAX | 6 | 59.00 | 3.47 | 2.78 | 2.34 | 1.78 | 1.50 | 1.28 | 0.95 | 1.13 | 0.18 |
| MUC-MEL | 4 | 69.00 | 5.88 | 5.06 | 4.35 | 3.83 | 2.87 | 2.35 | 1.79 | 0.91 | 0.23 |
| MUC-PEK | 6 | 113.00 | 4.39 | 3.73 | 3.39 | 2.78 | 2.06 | 1.50 | 1.31 | 1.23 | 0.25 |
| MUC-SIN | 6 | 104.00 | 4.15 | 3.20 | 2.66 | 2.21 | 1.92 | 1.75 | 1.54 | 0.98 | 0.18 |
| STR-MIA | 4 | 63.00 | 3.87 | 2.86 | 2.26 | 1.83 | 1.45 | 1.10 | 1.00 | 0.84 | 0.10 |

#### Vega Skyfreight: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | 2000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CGN-LOS | 3 | 114.48 | 4.60 | 4.19 | 3.73 | 2.69 | 2.42 | 1.94 | 1.69 | 1.29 | 0.13 |
| DUS-KUL | 2 | 72.00 | 4.47 | 3.38 | 2.77 | 2.41 | 2.12 | 1.55 | 1.35 | 1.15 | 0.14 |
| DUS-PEK | 2 | 118.72 | 3.88 | 3.42 | 2.46 | 1.80 | 1.53 | 1.22 | 1.22 | 1.34 | 0.24 |
| FRA-MNL | 5 | 65.00 | 4.04 | 3.64 | 3.06 | 2.36 | 2.15 | 1.55 | 1.24 | 1.04 | 0.13 |
| HAM-DEL | 4 | 66.00 | 3.21 | 2.76 | 2.40 | 2.06 | 1.59 | 1.45 | 1.25 | 0.65 | 0.25 |
| HAM-DFW | 1 | 83.74 | 3.84 | 2.76 | 2.35 | 2.14 | 1.78 | 1.57 | 1.30 | 1.37 | 0.14 |
| HAM-PEK | 4 | 126.00 | 4.16 | 3.49 | 3.07 | 2.79 | 2.20 | 1.65 | 1.22 | 0.90 | 0.10 |
| HAM-SYD | 6 | 56.00 | 6.20 | 5.15 | 4.53 | 3.49 | 2.79 | 2.04 | 1.82 | 0.76 | 0.23 |
| MUC-LIM | 3 | 124.00 | 5.30 | 4.56 | 3.56 | 3.24 | 2.40 | 2.09 | 1.65 | 1.20 | 0.19 |
| MUC-NBO | 4 | 140.00 | 4.64 | 4.08 | 3.35 | 2.51 | 1.91 | 1.53 | 1.39 | 1.20 | 0.12 |
| MUC-ORD | 1 | 144.16 | 3.07 | 2.79 | 2.40 | 2.04 | 1.86 | 1.40 | 1.02 | 1.16 | 0.22 |
| STR-MIA | 6 | 117.00 | 3.69 | 3.28 | 2.53 | 2.18 | 1.77 | 1.27 | 1.16 | 0.68 | 0.15 |
| STR-YYZ | 5 | 122.00 | 2.93 | 2.40 | 2.06 | 1.77 | 1.49 | 1.36 | 1.24 | 1.19 | 0.18 |

#### Wayzata Air Cargo: rates (EUR per kg of chargeable weight)

| Lane | Transit (d) | Min (EUR) | <45 | 45+ | 100+ | 300+ | 500+ | 1000+ | Fuel/kg | Security/kg |
|---|---|---|---|---|---|---|---|---|---|---|
| CGN-DEL | 2 | 87.98 | 4.69 | 3.67 | 3.02 | 2.38 | 2.09 | 1.64 | 1.15 | 0.26 |
| CGN-EZE | 4 | 80.00 | 3.99 | 3.27 | 2.65 | 2.09 | 1.61 | 1.19 | 0.80 | 0.19 |
| CGN-LIM | 5 | 62.00 | 5.59 | 5.09 | 4.48 | 3.90 | 2.81 | 2.50 | 0.77 | 0.21 |
| CGN-SCL | 6 | 131.00 | 4.54 | 3.27 | 2.49 | 2.29 | 2.04 | 1.61 | 1.05 | 0.16 |
| DUS-BOG | 3 | 125.08 | 4.46 | 3.84 | 3.26 | 3.00 | 2.46 | 2.02 | 0.73 | 0.20 |
| DUS-NBO | 4 | 119.78 | 4.55 | 3.96 | 3.60 | 2.59 | 2.36 | 1.86 | 1.31 | 0.17 |
| DUS-TLV | 2 | 81.00 | 3.32 | 2.72 | 2.34 | 1.76 | 1.27 | 0.98 | 0.73 | 0.12 |
| FRA-ATL | 5 | 129.00 | 3.27 | 2.71 | 2.06 | 1.73 | 1.42 | 1.08 | 0.78 | 0.23 |
| FRA-DOH | 1 | 136.00 | 3.44 | 2.64 | 2.20 | 1.67 | 1.48 | 1.15 | 1.21 | 0.19 |
| FRA-EZE | 5 | 121.00 | 4.93 | 4.39 | 3.47 | 2.85 | 2.39 | 2.03 | 1.15 | 0.18 |
| FRA-JFK | 4 | 93.00 | 3.39 | 2.92 | 2.22 | 1.73 | 1.49 | 1.25 | 0.92 | 0.22 |
| FRA-LAX | 4 | 107.00 | 2.85 | 2.48 | 1.81 | 1.45 | 1.23 | 0.97 | 1.19 | 0.14 |
| FRA-MEX | 4 | 126.00 | 3.49 | 2.65 | 2.09 | 1.88 | 1.45 | 1.25 | 1.00 | 0.23 |
| FRA-NRT | 3 | 136.74 | 4.29 | 3.64 | 3.31 | 2.75 | 2.45 | 2.04 | 0.61 | 0.15 |
| HAM-EZE | 6 | 56.00 | 4.81 | 3.56 | 2.67 | 1.98 | 1.62 | 1.20 | 0.72 | 0.21 |
| HAM-HKG | 4 | 130.00 | 3.78 | 2.95 | 2.66 | 2.18 | 1.70 | 1.36 | 1.16 | 0.18 |
| HAM-TLV | 1 | 135.68 | 2.89 | 2.63 | 2.35 | 2.02 | 1.70 | 1.30 | 1.20 | 0.24 |
| MUC-CAI | 2 | 144.16 | 4.49 | 3.46 | 3.09 | 2.41 | 1.96 | 1.49 | 0.97 | 0.24 |
| MUC-DXB | 2 | 106.00 | 2.76 | 2.51 | 1.86 | 1.67 | 1.20 | 1.00 | 0.56 | 0.19 |
| MUC-EZE | 4 | 121.00 | 4.94 | 4.35 | 3.87 | 3.33 | 2.83 | 2.04 | 1.23 | 0.21 |
| MUC-ICN | 5 | 111.00 | 3.73 | 3.02 | 2.30 | 1.75 | 1.31 | 0.94 | 1.08 | 0.20 |
| MUC-MIA | 5 | 55.00 | 3.77 | 3.17 | 2.47 | 2.10 | 1.93 | 1.51 | 0.74 | 0.11 |
| MUC-NRT | 2 | 140.98 | 4.20 | 3.53 | 2.61 | 2.25 | 1.85 | 1.52 | 1.26 | 0.24 |
| MUC-PEK | 6 | 112.00 | 4.27 | 3.63 | 3.16 | 2.84 | 2.22 | 1.75 | 1.30 | 0.25 |
| MUC-SCL | 4 | 138.00 | 5.61 | 4.88 | 3.57 | 3.17 | 2.76 | 2.40 | 1.11 | 0.20 |
| STR-SGN | 5 | 71.00 | 4.41 | 4.01 | 3.29 | 2.60 | 2.39 | 1.82 | 0.95 | 0.12 |

### 4.5 Data anomalies worth knowing (do not "fix" them, price exactly as printed)

- **28 minimums are exactly an integer × 1.06** (e.g. Vega DUS-PEK 118.72 = 112 × 1.06, Kestrel FRA-MIA 137.80 = 130 × 1.06, Danube FRA-DXB 138.86 = 131 × 1.06). All other minimums are whole euros. Looks like a deliberate +6 % on selected lanes.
- **Two adjacent breaks with the same rate** (no saving from moving up a break): Yellowtail HAM-BOG (100=250), MUC-JNB (1000=2000), STR-LAX (100=250, 1000=2000); Cobalt MUC-MIA (1000=2000); Helix FRA-LAX (100=250, 1000=2000), HAM-HKG (1000=2000); Quetzal FRA-RUH, STR-SCL (1000=2000); Kestrel FRA-BOM, HAM-PEK (100=250); Vega DUS-PEK (1000=2000).
- No rate ever rises with weight (all lanes are monotonic). The minimum binds up to 9–48 kg depending on the lane (minimum ÷ first-bracket rate).
- The destinations on each sheet match that airline's `serves` list in `carrier-list.csv` exactly.

## 5. Lanes (portal + sheets)

- Portal: **114 lanes**, per origin: CGN 12, DUS 17, FRA 34, HAM 14, MUC 24, STR 13. 15 airlines (code name (lanes)): AU Aurelia Air Cargo (14), BX Borealis Freight Airways (13), FQ Fjordline Air Cargo (12), GN Gannet Airways (4), IB Ibisair Cargo (17), JP Juniper Cargo Lines (13), LM Lumen Air Cargo (13), MD Meridian Freightways (18), NV Nova Atlas Cargo (12), PL Polaris Air Logistics (16), RV Riverbend Airlines Cargo (13), SL Solace Air Cargo (13), TM Tamarind Airways (19), UV Ultraviolet Air Freight (18), XC Xenon Cargo Airlines (11).
- Sheets: 158 lane rows, 107 distinct lanes.
- Combined: **120 distinct lanes**. Only in sheets (no portal airline): CGN-LOS, FRA-BOM, FRA-DXB, HAM-PEK, MUC-HKG, MUC-MEL. Only on the portal: CGN-NBO, CGN-ORD, DUS-ATL, DUS-MIA, FRA-GRU, FRA-LOS, FRA-TLV, FRA-YYZ, HAM-GRU, HAM-YYZ, MUC-BKK, STR-BOM, STR-EZE.
- Destinations served only by email airlines (no sheet, no portal): **ASU, KTM, PPT, TNR, ULN** (Zephyr Steppe, Himalaya Bridge, Lagoon Isles, Pampero). The ports endpoint says missing destinations are "priced by email to the airline".

| Origin | Dest | Portal airlines (code) | Sheet airlines | Total |
|---|---|---|---|---|
| CGN | DEL | JP Juniper Cargo Lines, UV Ultraviolet Air Freight | Wayzata Air Cargo | 3 |
| CGN | DFW | LM Lumen Air Cargo, UV Ultraviolet Air Freight | Quetzal Air Freight | 3 |
| CGN | EZE | UV Ultraviolet Air Freight | Cobalt Skylift, Wayzata Air Cargo | 3 |
| CGN | LIM | NV Nova Atlas Cargo, XC Xenon Cargo Airlines | Wayzata Air Cargo | 3 |
| CGN | LOS | — | Helix Air Freight, Quetzal Air Freight, Elbflug Air Freight, Vega Skyfreight | 4 |
| CGN | MIA | LM Lumen Air Cargo | Orion Cargo Air, Kestrel Airways | 3 |
| CGN | NBO | AU Aurelia Air Cargo, FQ Fjordline Air Cargo, TM Tamarind Airways | — | 3 |
| CGN | ORD | AU Aurelia Air Cargo, IB Ibisair Cargo, MD Meridian Freightways, XC Xenon Cargo Airlines | — | 4 |
| CGN | SCL | BX Borealis Freight Airways | Wayzata Air Cargo | 2 |
| CGN | SGN | JP Juniper Cargo Lines, LM Lumen Air Cargo | Cobalt Skylift | 3 |
| CGN | SIN | FQ Fjordline Air Cargo, UV Ultraviolet Air Freight | Cobalt Skylift | 3 |
| CGN | SYD | NV Nova Atlas Cargo | Yellowtail Air Freight, Danube Wings Cargo, Helix Air Freight | 4 |
| CGN | TLV | TM Tamarind Airways | Orion Cargo Air | 2 |
| DUS | ATL | MD Meridian Freightways, PL Polaris Air Logistics, RV Riverbend Airlines Cargo, SL Solace Air Cargo | — | 4 |
| DUS | BOG | RV Riverbend Airlines Cargo | Wayzata Air Cargo | 2 |
| DUS | BOM | FQ Fjordline Air Cargo, LM Lumen Air Cargo, XC Xenon Cargo Airlines | Cobalt Skylift | 4 |
| DUS | DEL | FQ Fjordline Air Cargo | Cobalt Skylift | 2 |
| DUS | DFW | MD Meridian Freightways | Kestrel Airways | 2 |
| DUS | HKG | IB Ibisair Cargo | Quetzal Air Freight, Elbflug Air Freight | 3 |
| DUS | JFK | FQ Fjordline Air Cargo, UV Ultraviolet Air Freight | Yellowtail Air Freight, Cobalt Skylift | 4 |
| DUS | KUL | FQ Fjordline Air Cargo | Kestrel Airways, Vega Skyfreight | 3 |
| DUS | MEX | TM Tamarind Airways, UV Ultraviolet Air Freight, XC Xenon Cargo Airlines | Danube Wings Cargo | 4 |
| DUS | MIA | AU Aurelia Air Cargo, RV Riverbend Airlines Cargo, TM Tamarind Airways, XC Xenon Cargo Airlines | — | 4 |
| DUS | NBO | IB Ibisair Cargo, MD Meridian Freightways | Wayzata Air Cargo | 3 |
| DUS | NRT | BX Borealis Freight Airways | Kestrel Airways | 2 |
| DUS | PEK | GN Gannet Airways | Vega Skyfreight | 2 |
| DUS | RUH | AU Aurelia Air Cargo, RV Riverbend Airlines Cargo | Helix Air Freight | 3 |
| DUS | SYD | JP Juniper Cargo Lines, NV Nova Atlas Cargo | Danube Wings Cargo, Cobalt Skylift | 4 |
| DUS | TLV | RV Riverbend Airlines Cargo, UV Ultraviolet Air Freight | Elbflug Air Freight, Wayzata Air Cargo | 4 |
| DUS | YYZ | AU Aurelia Air Cargo, JP Juniper Cargo Lines, TM Tamarind Airways | Danube Wings Cargo | 4 |
| FRA | ATL | FQ Fjordline Air Cargo, IB Ibisair Cargo | Wayzata Air Cargo | 3 |
| FRA | BKK | IB Ibisair Cargo, TM Tamarind Airways | Yellowtail Air Freight | 3 |
| FRA | BOG | IB Ibisair Cargo | Cobalt Skylift, Elbflug Air Freight | 3 |
| FRA | BOM | — | Quetzal Air Freight, Kestrel Airways | 2 |
| FRA | CAI | BX Borealis Freight Airways, MD Meridian Freightways | Kestrel Airways | 3 |
| FRA | DEL | MD Meridian Freightways, SL Solace Air Cargo | Kestrel Airways | 3 |
| FRA | DFW | RV Riverbend Airlines Cargo | Yellowtail Air Freight, Elbflug Air Freight | 3 |
| FRA | DOH | RV Riverbend Airlines Cargo, UV Ultraviolet Air Freight | Wayzata Air Cargo | 3 |
| FRA | DXB | — | Danube Wings Cargo, Elbflug Air Freight | 2 |
| FRA | EZE | JP Juniper Cargo Lines, TM Tamarind Airways | Danube Wings Cargo, Wayzata Air Cargo | 4 |
| FRA | GRU | JP Juniper Cargo Lines, RV Riverbend Airlines Cargo | — | 2 |
| FRA | HKG | MD Meridian Freightways, PL Polaris Air Logistics | Elbflug Air Freight | 3 |
| FRA | ICN | GN Gannet Airways, PL Polaris Air Logistics | Cobalt Skylift | 3 |
| FRA | JFK | PL Polaris Air Logistics, SL Solace Air Cargo | Wayzata Air Cargo | 3 |
| FRA | JNB | FQ Fjordline Air Cargo, TM Tamarind Airways | Cobalt Skylift | 3 |
| FRA | KUL | PL Polaris Air Logistics | Orion Cargo Air | 2 |
| FRA | LAX | GN Gannet Airways, MD Meridian Freightways | Helix Air Freight, Wayzata Air Cargo | 4 |
| FRA | LIM | AU Aurelia Air Cargo | Yellowtail Air Freight, Quetzal Air Freight | 3 |
| FRA | LOS | LM Lumen Air Cargo, TM Tamarind Airways | — | 2 |
| FRA | MEL | JP Juniper Cargo Lines, NV Nova Atlas Cargo | Elbflug Air Freight | 3 |
| FRA | MEX | TM Tamarind Airways | Kestrel Airways, Wayzata Air Cargo | 3 |
| FRA | MIA | MD Meridian Freightways, SL Solace Air Cargo | Elbflug Air Freight, Kestrel Airways | 4 |
| FRA | MNL | UV Ultraviolet Air Freight | Vega Skyfreight | 2 |
| FRA | NBO | JP Juniper Cargo Lines, UV Ultraviolet Air Freight | Yellowtail Air Freight, Orion Cargo Air | 4 |
| FRA | NRT | LM Lumen Air Cargo | Kestrel Airways, Wayzata Air Cargo | 3 |
| FRA | ORD | BX Borealis Freight Airways | Yellowtail Air Freight, Orion Cargo Air | 3 |
| FRA | PEK | LM Lumen Air Cargo | Orion Cargo Air | 2 |
| FRA | PVG | NV Nova Atlas Cargo | Helix Air Freight | 2 |
| FRA | RUH | TM Tamarind Airways | Quetzal Air Freight | 2 |
| FRA | SCL | AU Aurelia Air Cargo, UV Ultraviolet Air Freight | Helix Air Freight | 3 |
| FRA | SGN | PL Polaris Air Logistics | Orion Cargo Air, Elbflug Air Freight | 3 |
| FRA | SIN | NV Nova Atlas Cargo | Elbflug Air Freight | 2 |
| FRA | SYD | SL Solace Air Cargo | Cobalt Skylift | 2 |
| FRA | TLV | AU Aurelia Air Cargo, FQ Fjordline Air Cargo, GN Gannet Airways | — | 3 |
| FRA | TPE | JP Juniper Cargo Lines, NV Nova Atlas Cargo, SL Solace Air Cargo | Cobalt Skylift | 4 |
| FRA | YYZ | BX Borealis Freight Airways, RV Riverbend Airlines Cargo, UV Ultraviolet Air Freight | — | 3 |
| HAM | BOG | RV Riverbend Airlines Cargo, SL Solace Air Cargo | Yellowtail Air Freight, Cobalt Skylift | 4 |
| HAM | DEL | BX Borealis Freight Airways, IB Ibisair Cargo | Vega Skyfreight | 3 |
| HAM | DFW | MD Meridian Freightways | Elbflug Air Freight, Vega Skyfreight | 3 |
| HAM | DXB | TM Tamarind Airways | Orion Cargo Air, Elbflug Air Freight | 3 |
| HAM | EZE | MD Meridian Freightways | Wayzata Air Cargo | 2 |
| HAM | GRU | FQ Fjordline Air Cargo, IB Ibisair Cargo, RV Riverbend Airlines Cargo, UV Ultraviolet Air Freight | — | 4 |
| HAM | HKG | TM Tamarind Airways | Helix Air Freight, Kestrel Airways, Wayzata Air Cargo | 4 |
| HAM | JFK | IB Ibisair Cargo | Quetzal Air Freight | 2 |
| HAM | MEX | RV Riverbend Airlines Cargo | Yellowtail Air Freight, Elbflug Air Freight | 3 |
| HAM | PEK | — | Kestrel Airways, Vega Skyfreight | 2 |
| HAM | RUH | LM Lumen Air Cargo, TM Tamarind Airways | Cobalt Skylift | 3 |
| HAM | SGN | JP Juniper Cargo Lines, PL Polaris Air Logistics | Yellowtail Air Freight | 3 |
| HAM | SYD | IB Ibisair Cargo, MD Meridian Freightways, UV Ultraviolet Air Freight | Vega Skyfreight | 4 |
| HAM | TLV | MD Meridian Freightways | Elbflug Air Freight, Wayzata Air Cargo | 3 |
| HAM | YYZ | BX Borealis Freight Airways, JP Juniper Cargo Lines, LM Lumen Air Cargo, PL Polaris Air Logistics | — | 4 |
| MUC | BKK | NV Nova Atlas Cargo, PL Polaris Air Logistics | — | 2 |
| MUC | BOG | LM Lumen Air Cargo, XC Xenon Cargo Airlines | Cobalt Skylift, Elbflug Air Freight | 4 |
| MUC | CAI | AU Aurelia Air Cargo, BX Borealis Freight Airways | Wayzata Air Cargo | 3 |
| MUC | DXB | LM Lumen Air Cargo | Quetzal Air Freight, Wayzata Air Cargo | 3 |
| MUC | EZE | MD Meridian Freightways | Quetzal Air Freight, Wayzata Air Cargo | 3 |
| MUC | GRU | SL Solace Air Cargo | Orion Cargo Air, Kestrel Airways | 3 |
| MUC | HKG | — | Helix Air Freight, Orion Cargo Air | 2 |
| MUC | ICN | IB Ibisair Cargo, PL Polaris Air Logistics | Wayzata Air Cargo | 3 |
| MUC | JNB | PL Polaris Air Logistics | Yellowtail Air Freight, Danube Wings Cargo | 3 |
| MUC | LAX | FQ Fjordline Air Cargo | Yellowtail Air Freight, Kestrel Airways | 3 |
| MUC | LIM | BX Borealis Freight Airways | Cobalt Skylift, Vega Skyfreight | 3 |
| MUC | MEL | — | Cobalt Skylift, Kestrel Airways | 2 |
| MUC | MEX | IB Ibisair Cargo, SL Solace Air Cargo | Cobalt Skylift | 3 |
| MUC | MIA | IB Ibisair Cargo | Cobalt Skylift, Wayzata Air Cargo | 3 |
| MUC | NBO | TM Tamarind Airways | Orion Cargo Air, Vega Skyfreight | 3 |
| MUC | NRT | NV Nova Atlas Cargo, SL Solace Air Cargo, XC Xenon Cargo Airlines | Wayzata Air Cargo | 4 |
| MUC | ORD | XC Xenon Cargo Airlines | Vega Skyfreight | 2 |
| MUC | PEK | IB Ibisair Cargo, PL Polaris Air Logistics | Kestrel Airways, Wayzata Air Cargo | 4 |
| MUC | PVG | MD Meridian Freightways, XC Xenon Cargo Airlines | Helix Air Freight | 3 |
| MUC | RUH | JP Juniper Cargo Lines, UV Ultraviolet Air Freight | Quetzal Air Freight | 3 |
| MUC | SCL | BX Borealis Freight Airways, PL Polaris Air Logistics | Wayzata Air Cargo | 3 |
| MUC | SGN | NV Nova Atlas Cargo, PL Polaris Air Logistics, TM Tamarind Airways | Helix Air Freight | 4 |
| MUC | SIN | AU Aurelia Air Cargo, IB Ibisair Cargo | Kestrel Airways | 3 |
| MUC | SYD | BX Borealis Freight Airways, PL Polaris Air Logistics | Elbflug Air Freight | 3 |
| MUC | TPE | MD Meridian Freightways | Danube Wings Cargo | 2 |
| MUC | YYZ | AU Aurelia Air Cargo, LM Lumen Air Cargo, RV Riverbend Airlines Cargo | Cobalt Skylift | 4 |
| STR | BOM | IB Ibisair Cargo, UV Ultraviolet Air Freight, XC Xenon Cargo Airlines | — | 3 |
| STR | EZE | AU Aurelia Air Cargo, FQ Fjordline Air Cargo, NV Nova Atlas Cargo | — | 3 |
| STR | LAX | AU Aurelia Air Cargo, PL Polaris Air Logistics, UV Ultraviolet Air Freight | Yellowtail Air Freight | 4 |
| STR | MEL | AU Aurelia Air Cargo, SL Solace Air Cargo | Yellowtail Air Freight | 3 |
| STR | MIA | MD Meridian Freightways, SL Solace Air Cargo | Kestrel Airways, Vega Skyfreight | 4 |
| STR | MNL | MD Meridian Freightways, TM Tamarind Airways | Yellowtail Air Freight, Orion Cargo Air | 4 |
| STR | ORD | NV Nova Atlas Cargo | Helix Air Freight, Elbflug Air Freight | 3 |
| STR | PEK | BX Borealis Freight Airways | Orion Cargo Air | 2 |
| STR | PVG | LM Lumen Air Cargo, TM Tamarind Airways | Helix Air Freight, Elbflug Air Freight | 4 |
| STR | SCL | JP Juniper Cargo Lines, XC Xenon Cargo Airlines | Quetzal Air Freight | 3 |
| STR | SGN | BX Borealis Freight Airways | Danube Wings Cargo, Wayzata Air Cargo | 3 |
| STR | TLV | SL Solace Air Cargo, UV Ultraviolet Air Freight | Orion Cargo Air | 3 |
| STR | YYZ | IB Ibisair Cargo, TM Tamarind Airways | Cobalt Skylift, Vega Skyfreight | 4 |

## 6. Pricing formula and worked examples

```
chargeable_kg = max(actual_kg, cbm × 167)
for each break b_i ≥ bracket(chargeable_kg):           # own bracket + every higher break
    billed_kg = chargeable_kg if own bracket else b_i
    freight   = max(minimum, rate_i × billed_kg)        # minimum before surcharges
    total_i   = freight + (fuel + security) × billed_kg # surcharges on the billed weight
price = min(total_i)                                    # then compare across airlines/sources
```

Open points the kit does not settle: rounding of chargeable weight (none stated; the portal returns `chargeable_weight_kg` as a string, compare with one portal call), and rounding of components. The examples round freight and surcharges half-up to cents and add them; rounding only the unrounded sum can differ by 1 cent (Wayzata below: 1160.66 vs 1160.65). Check against one portal `total`.

1. Minimum charge binds, surcharges still per kg:

**Vega Skyfreight MUC-ORD**, 40 kg, 0.1 cbm → volume weight 0.1 × 167 = 16.7 kg → chargeable **40 kg**. Fuel 1.16 + security 0.22 = 1.38/kg. Min 144.16. Transit 1 d.

- <45 @ 3.07 × 40 kg (own bracket): freight 144.16 (minimum applies) + surcharges 55.20 = **199.36**  ← cheapest
- 45+ @ 2.79 × 45 kg (billed as next break): freight 144.16 (minimum applies) + surcharges 62.10 = **206.26**
- 100+ @ 2.40 × 100 kg (billed as next break): freight 240.00 + surcharges 138.00 = **378.00**

2. Next-break check (billing at 100 kg is cheaper than 90 kg; surcharges are then charged on the 100 kg billed):

**Yellowtail Air Freight FRA-ORD**, 90 kg, 0.4 cbm → volume weight 0.4 × 167 = 66.8 kg → chargeable **90 kg**. Fuel 0.66 + security 0.11 = 0.77/kg. Min 110.00. Transit 4 d.

- 45+ @ 3.32 × 90 kg (own bracket): freight 298.80 + surcharges 69.30 = **368.10**
- 100+ @ 2.42 × 100 kg (billed as next break): freight 242.00 + surcharges 77.00 = **319.00**  ← cheapest
- 250+ @ 1.82 × 250 kg (billed as next break): freight 455.00 + surcharges 192.50 = **647.50**

3. Volume weight dominates, two sheets on the same lane, cheapest ≠ fastest:

**Helix Air Freight FRA-LAX**, 300 kg, 2.5 cbm → volume weight 2.5 × 167 = 417.5 kg → chargeable **417.5 kg**. Fuel 1.40 + security 0.21 = 1.61/kg. Min 112.00. Transit 1 d.

- 250+ @ 2.24 × 417.5 kg (own bracket): freight 935.20 + surcharges 672.18 = **1607.38**  ← cheapest
- 500+ @ 1.62 × 500 kg (billed as next break): freight 810.00 + surcharges 805.00 = **1615.00**
- 1000+ @ 1.25 × 1000 kg (billed as next break): freight 1250.00 + surcharges 1610.00 = **2860.00**

**Wayzata Air Cargo FRA-LAX**, 300 kg, 2.5 cbm → volume weight 2.5 × 167 = 417.5 kg → chargeable **417.5 kg**. Fuel 1.19 + security 0.14 = 1.33/kg. Min 107.00. Transit 4 d.

- 300+ @ 1.45 × 417.5 kg (own bracket): freight 605.38 + surcharges 555.28 = **1160.66**  ← cheapest
- 500+ @ 1.23 × 500 kg (billed as next break): freight 615.00 + surcharges 665.00 = **1280.00**
- 1000+ @ 0.97 × 1000 kg (billed as next break): freight 970.00 + surcharges 1330.00 = **2300.00**

→ Wayzata EUR 1160.66 (4 d) vs Helix EUR 1607.38 (1 d). Portal airlines on FRA-LAX (GN, MD) must be checked too before quoting.

## 7. Pricing traps

- **Units:** RFQs may use lb/in (our own fixture `rfq_001` does). 1 lb = 0.45359237 kg, 1 in = 2.54 cm. Volume weight uses cbm × 167 (dims in cm: L×W×H/1,000,000 × 167), not ÷ 6000 (difference: 167 vs 166.67 kg per cbm, enough to miss a break edge or the 5 % band on big shipments).
- **Decimals and number types:** comma decimals in Danube, Elbflug, Kestrel, Orion, Quetzal; dot in Cobalt, Helix, Vega, Wayzata, Yellowtail. Elbflug and Kestrel store numbers as text.
- **Break labels:** "-45" = below 45 kg, "+45" = from 45 kg; "from 0 kg", "0 kg+" all mean the first bracket. 250 vs 300 break and the presence of a 2000 break differ per airline (§4.2).
- **Next-break check:** compute every higher break too, and remember the surcharges then apply to the higher billed weight (example 2). The portal does not do this for us: it prices "in that weight's bracket", so it may be worth asking the portal for the next break weight as well (costs rate-limited reads).
- **Minimum before surcharges:** never compare the minimum against the all-in total (example 1).
- **Currency:** sheets are EUR; portal rates can come in another currency with `fx_eur_per_usd` (EUR per 1 unit of that currency). Convert before comparing; quote one all-in total with its currency.
- **Validity:** all sheets end 30 Nov 2026. RFQs with a December ship date need the new monthly tariffs that airlines send by mail (the mailbox doc lists "airline tariff mails"). Portal rate IDs carry `valid_until`; an expired rate_id gets 410 on booking.
- **Transit formats:** integer, "N days", "1 day", "D+N". Cheapest and fastest often differ (example 3: Wayzata 4 d vs Helix 1 d on FRA-LAX).
- **Places:** customer city → origin airport through `pickup_zones.csv` for door-to-port (Bremen → HAM, Bonn → CGN, Mainz → FRA, Augsburg → MUC …); cities with several real airports where the kit only knows one: New York (JFK, not EWR/LGA), Tokyo (NRT, not HND), Shanghai (PVG, not SHA), Beijing (PEK, not PKX), São Paulo (GRU, not CGH/VCP), Dubai (DXB, not DWC), Bangkok (BKK, not DMK), Buenos Aires (EZE, not AEP), Mexico City (MEX, not NLU), Chicago (ORD, not MDW), Dallas (DFW, not DAL). Also "Saigon" = SGN, "Bombay" = BOM, "New Delhi" = DEL.
- **Door-to-port:** only truckers that serve the pickup zone may be asked (e.g. zone 45 Essen: 5 truckers; zone 35 Giessen: 2). Some zones have few truckers; mailing all 22 truckers wastes the 60 mails/min limit and replies.
- **Several sources per lane:** each lane has 2–4 sources (portal airlines + sheet airlines + email bids). The accepted band is 5 % of the best price, so a missing source easily costs the quote.
- **Odd minimums** (×1.06) and **duplicate break rates** (§4.5) look planted: they change which break or minimum wins.

## 8. API (from `openapi.json`, "Hackathon API" 0.1.0)

Base URL `https://api.start-hack.5u.ai`. Auth: header `X-API-Key: <team key>` (the spec declares no security scheme; the docs say "Send your key as `X-API-Key`"). The start kit itself downloads with the same header.

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | 200 when Postgres answers, 503 otherwise |
| GET | `/v1/me` | Who the key belongs to (team, display_name, mailbox) |
| GET | `/v1/mailbox/messages?since_id=&limit=` | Poll mail **to** us with `id > since_id`, oldest first, max 200 per call. Keep `next_since_id`. No push: poll every 1–2 s (response time counts). Items carry `references` (thread ids from first mail down to the parent) and `attachments` (id, filename, content type, size). Everything arrives here: customer RFQs, carrier bids, rate desk answers, booking confirmations, airline tariff mails, tracking questions |
| POST | `/v1/mailbox/messages` | Send `{to, subject, body, in_reply_to, attachments[]}` → 201. A quote counts only as a reply (`in_reply_to`) in a thread a customer started, and **only our first quote in a thread counts**. `in_reply_to` must be a mail we sent/received, else 404. Allowed recipients: customers, carrier-list airlines/truckers, `ratedesk@hackloop.mail`, `tracking@hackloop.mail`; anything else 422. Attachments max 5 × 10 MB, types pdf/xlsx/xls/csv/txt/png/jpg/docx (`content_base64`). **Limit 60 mails/min**, then 429 |
| GET | `/v1/mailbox/messages/{id}` | One message we sent or received |
| GET | `/v1/mailbox/messages/{id}/attachments/{attachment_id}` | Raw attachment bytes |
| GET | `/v1/portal/ports` | Every lane the portal can price with its airlines `{code, name}`. Missing destinations are priced by email to the airline |
| GET | `/v1/portal/brackets?airline=` | An airline's weight breaks (`breaks_kg`, a bracket runs from its break to the next). Non-portal airline → 404 with the address to email |
| GET | `/v1/portal/rates?origin=&destination=&airline=&weight_kg=&volume_cbm=` | One priced rate: `rate_id`, airline, airline_code, origin, destination, weight_kg, `chargeable_weight_kg` (= max(weight, cbm × 167)), `total` (freight + fuel + security, 2-decimal string), `currency`, `fx_eur_per_usd` (only if not EUR), `transit_days`, `valid_until` (ISO), `dataset_version`. Priced **in that weight's bracket**. **Rate-limited per team per fixed 1-min window** (429 + `Retry-After`; headers `X-RateLimit-Limit` / `X-RateLimit-Remaining`). Ports and brackets don't count. 503 = unavailable, message says where to get the rate instead |
| POST | `/v1/portal/bookings` | `{rate_id: "R-…", team_reference}` → 201 booked (`booking_reference` "BK-" + 8 chars, price, currency, status `booked`); 200 = same retry; 404 unknown/other team's rate_id; 409 already booked under another reference; **410 expired** (fetch fresh rate); 503 = book by email with the airline (message says how). Confirmation mail "Booking <ref> confirmed" follows; **no status endpoint**, keep it in our CRM. Bookings don't count against the rate limit |
| GET | `/v1/gateway/openai-key` | Whether our own OpenAI key is stored (`set`, `last4`, `checked_at`); the key itself is never returned |
| POST | `/v1/gateway/openai-key` | Store our own OpenAI key `{api_key}` (checked with one tiny call; replaces the old one) |
| GET | `/v1/gateway/models` | Allowed models (OpenAI list shape) |
| POST | `/v1/gateway/chat/completions` | OpenAI Chat Completions incl. `stream: true` |
| POST | `/v1/gateway/responses` | OpenAI Responses incl. `stream: true` |
| POST | `/v1/gateway/embeddings` | OpenAI Embeddings |
| GET | `/v1/board` | Public leaderboard: rank, team, total, accepted, answered per team, every booking (newest first, no price), last 10 rounds. Cost points are added once an hour, up to ~1 h after a quote. `frozen_at` set when frozen |
| GET | `/v1/board/me` | Our result per request: round, sent/answered time, verdict (`accepted`, `rejected`, `pending`, `open`, `no answer`, `voided`), reason code, points per kind, booked y/n, request total; plus our bookings |

## 9. API snapshots (`kit/api-snapshots/`, taken ~14:25)

- `GET /v1/me` → team `leylu`, display name "Leylü", mailbox `leylu@hackloop.mail`.
- `GET /v1/gateway/openai-key` → first call ~14:25 local: `set: false`; re-checked ~14:50: **`set: true`, `checked_at` 2026-11-21T13:30:11Z** (file now holds the second response; `last4` not reproduced here).
- `GET /v1/gateway/models` → 32 models: `chat-latest`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `gpt-5`, `gpt-5.1`, `gpt-5.2`, `gpt-5.2-pro`, `gpt-5.3-codex`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.4-pro`, `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6-astra`, `gpt-6-luna`, `gpt-6-sol`, `o3`, `text-embedding-3-large`, `text-embedding-3-small`.
- `GET /v1/portal/ports` → 114 lanes (§5).
- `GET /v1/board` → not frozen; 14 teams, 0 rounds sent, 0 accepted, 0 bookings. Rules object: `accuracy_points 45, time_points 15, cost_points 40, humanity_points 10, tracking_points 10`. Teams: AEIOU, ATLA, Austrian Power, BLACKBOX, FREE CANDY, Google, Leylü, MAKEANOTHERMD, Mythos, PIXEL, REISY, START Milan, TALOS, WRATHOFCODE. Ranking rows carry a per-team `human` field (humanity may be scored per request, not only as a one-off jury bonus).
- Not called on purpose: `/v1/portal/rates`, `/v1/portal/bookings`, `/v1/portal/brackets`, mailbox poll/send, any POST.

## 10. Repo vs kit conflicts (repo state ~14:50: `main` @ 8448373, and PR #14 `orhun/L2-contract-make-ci` (open) which rewrites Makefile, CONTRACT.md, .env.example, AGENTS.md)

| # | Where in the repo | Repo says | Kit / API says | Impact |
|---|---|---|---|---|
| 1 | root `.env` (just created) × `agent/llm.py` | `MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")` | `.env` has `LLM_MODEL=` (empty) → `uv run --env-file ../.env` and `load_dotenv` both set it to `''`, so the default is **not** used | `chat_json` raises `KeyError: No price for ` → every RFQ extraction fails. Fix: set `LLM_MODEL=gpt-4o-mini` in `.env` or delete the line (or treat empty as unset in `llm.py`) |
| 2 | `agent/setup_5u.py`, `AGENTS.md` gotcha, `agent/AGENTS.md` | Needs `GATEWAY_OPENAI_KEY` (our own OpenAI key) in `.env` and stores it via `POST /v1/gateway/openai-key` | Gateway status was `set: false` at 14:25, `set: true` since 13:30 UTC | Resolved on the server: key stored 13:30 UTC (PR #12). Only matters again if the key is rotated; our `.env` still has no `GATEWAY_OPENAI_KEY`, so `setup_5u.py` works only because the key is already stored |
| 3 | `docs/PLAN.md` §1/§8 (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MAILBOX_*`, `PORTAL_*`); `docs/CONTRACT.md` + `.env.example` (`LLM_API_KEY`, `PORT=3000`, `MOCK_API`) | Different env var names in every file | Code actually reads `FIVEU_API_KEY`, `FIVEU_BASE_URL`, `GATEWAY_OPENAI_KEY`, `LLM_MODEL`, `BACKEND_URL`, `MOCK`, `SINCE_ID_FILE`, `BID_CUTOFF_SECONDS`, `FIXTURE_INBOX`, `CARRIERS_FILE`. Our `.env` adds `OPENAI_BASE_URL`/`OPENAI_API_KEY` (unused by code; `llm.py` passes explicit values) and `PORT=8000` | PR #14 (L2, open) rewrites `.env.example`/CONTRACT to `FIVEU_BASE_URL, FIVEU_API_KEY, GATEWAY_OPENAI_KEY, LLM_MODEL=gpt-4o-mini, BACKEND_URL, PORT=8000, BID_CUTOFF_SECONDS`. Our local `.env` then differs: extra `OPENAI_*`, empty `LLM_MODEL`, no `GATEWAY_OPENAI_KEY`/`BACKEND_URL`/`BID_CUTOFF_SECONDS` (defaults apply) |
| 4 | `docs/PLAN.md` §6 "Chargeable weight … ÷ divisor (often 6000)" | ÷ 6000 | 1 cbm = 167 kg everywhere (≈ ÷ 5988) | Wrong chargeable weight on volume-heavy shipments |
| 5 | `docs/PLAN.md` §6 "Surcharges: actual or chargeable? per-AWB fees, currency" | Open question | Per kg of the **billed** weight; no per-AWB fees; sheets all EUR, portal may be non-EUR with `fx_eur_per_usd` | Answered: close the ❓ |
| 6 | `agent/fixtures/carriers.json`, `agent/carriers.py` | 3 placeholder carriers (`*.example` addresses), truckers have no zones; `carriers_for` mails **all** truckers when there is a pickup; airlines matched on destination only | `carrier-list.csv`: 29 airlines (serves = destinations) + 22 truckers (serves = pickup zones); mail to any other address → 422 | Live bid requests would fail (422). Needs a CSV → JSON conversion and zone filtering for truckers |
| 7 | `docs/PLAN.md` §7 / `frontend/lib/mock.ts` | Pickup zone like `"Z2"` with a zone price ("Pickup zone Z2 … 16.00"; the PR #14 CONTRACT keeps "else the pickup-zone price"); one mock session picks up in Milano / flies from MXP | Zones are 2-digit postcode prefixes (`"60"`), mapped to an airport; **no zone prices** in the kit | Trucker cost must come from trucker bids, not a table. Origins are only the 6 German airports (no MXP) |
| 8 | `docs/PLAN.md` §1, TASKS B4 "rate ID valid 15 min" | 15 min | API only says `valid_until` (ISO) per rate; 410 when expired | Use `valid_until`, not a fixed 15 min |
| 9 | TASKS B2/B3, PLAN §1 "10 rate sheets" | 10 sheets | 10 airlines but **11 files** (Danube = 2 JPG photos, needs OCR/vision) | Parser for images needed (or hand-entered once; data is in `kit/tariffs.normalized.json`) |
| 10 | `agent/inbox.py` | Poll response parsed as `{messages, next_since_id}`; sender read from `from` or `sender` | OpenAPI documents `next_since_id`, `references`, `attachments`, but the response schema is untyped (`additionalProperties`) | Unverified until the first real poll (`setup_5u.py` step 4 checks it) |
| 11 | `agent/llm.py` `PRICES` | gpt-4o-mini, gpt-4.1-mini, gpt-5-nano, gpt-5-mini | All 4 are in the gateway list ✓ (older `gpt-4.1-nano` default was not, fixed in PR #12) | OK now |
| 12 | `docs/PLAN.md` §2 scoring | 45 / 40 / 15 + tracking +10 + jury +10 | Board rules: accuracy 45, cost 40, time 15, humanity 10, tracking 10 ✓; board has a per-team `human` counter | Humanity may be scored per request, worth asking 5U |
| 13 | `AGENTS.md` "Run: make dev (uses PORT env, default 3000)" | PORT 3000 | Our `.env` `PORT=8000`; new Makefile runs backend on `${PORT:-8000}` and frontend on 3000 | PR #14 sets `PORT=8000` = backend, frontend on 3000 |
| 14 | `agent/carriers.py` `MAX_AIRLINES = 5` (first 5 in file order) | First 5 matching airlines | Up to 14+ airlines serve popular destinations (e.g. SYD), but per lane only 2–4 have prices; bids are per destination | Choose which airlines to ask by lane coverage, not file order |

## 11. Open questions for 5U (not answered by the kit)

1. Rounding of chargeable weight (0.5 kg / 1 kg / none)?
2. How to book a sheet airline or an email-bid rate (no portal `rate_id`)? Booking by email to the airline?
3. Do the sheet airlines' prices equal what the "best price" check uses, or does the checker use the portal/dataset version (`dataset_version` on rates)?
4. Is LLM spend outside the gateway (e.g. parsing sheets at build time) allowed / counted?
5. Is humanity scored per request (board has a `human` field)?
