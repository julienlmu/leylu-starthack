// IATA code → city for the airports in the kit and the sample night (agent/quote_style.py CITIES + MXP).
const CITIES: Record<string, string> = {
  MUC: "Munich", FRA: "Frankfurt", DUS: "Düsseldorf", CGN: "Cologne", HAM: "Hamburg", STR: "Stuttgart", BER: "Berlin",
  HAJ: "Hanover", LEJ: "Leipzig", NUE: "Nuremberg", MXP: "Milan", AMS: "Amsterdam", LHR: "London", CDG: "Paris",
  JFK: "New York", EWR: "Newark", ORD: "Chicago", LAX: "Los Angeles", DFW: "Dallas", MIA: "Miami", ATL: "Atlanta",
  IAH: "Houston", SFO: "San Francisco", BOS: "Boston", SEA: "Seattle", YYZ: "Toronto", YUL: "Montreal",
  MEX: "Mexico City", GRU: "São Paulo", EZE: "Buenos Aires", SCL: "Santiago", BOG: "Bogotá", LIM: "Lima",
  PVG: "Shanghai", PEK: "Beijing", CAN: "Guangzhou", HKG: "Hong Kong", TPE: "Taipei", ICN: "Seoul", NRT: "Tokyo",
  HND: "Tokyo", KIX: "Osaka", SGN: "Ho Chi Minh City", HAN: "Hanoi", BKK: "Bangkok", SIN: "Singapore",
  KUL: "Kuala Lumpur", CGK: "Jakarta", MNL: "Manila", DEL: "Delhi", BOM: "Mumbai", BLR: "Bengaluru", MAA: "Chennai",
  DXB: "Dubai", AUH: "Abu Dhabi", DOH: "Doha", RUH: "Riyadh", JED: "Jeddah", TLV: "Tel Aviv", IST: "Istanbul",
  CAI: "Cairo", LOS: "Lagos", NBO: "Nairobi", JNB: "Johannesburg", CPT: "Cape Town", ADD: "Addis Ababa",
  SYD: "Sydney", MEL: "Melbourne", AKL: "Auckland",
};

// The city, else the code as written.
export const city = (code: string) => CITIES[code.toUpperCase()] ?? code;
