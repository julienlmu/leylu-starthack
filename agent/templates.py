"""Customer mail templates. Written by hand, not by the LLM (cost), and meant to read human.

shortcut: English placeholder wording; task U4 (Ulas) replaces it with the final templates and languages.
"""


def _pieces(rfq: dict) -> str:
    lines = []
    for p in rfq["pieces"]:
        dims = f"{p['length_cm']:g} x {p['width_cm']:g} x {p['height_cm']:g} cm, " if p["length_cm"] else ""
        lines.append(f"{p['count']} pcs, {dims}{p['weight_kg']:g} kg each")
    if rfq.get("volume_m3"):
        lines.append(f"total volume {rfq['volume_m3']:g} m³")
    return "; ".join(lines)


def bid_request_text(rfq: dict, kind: str) -> str:
    """Bid request to an airline or trucker. The answer format we ask for lets bids.parse_bid read it for free."""
    if kind == "trucker":
        service = f"pickup from {rfq['pickup']['address']} to {rfq['origin']} airport"
    else:
        service = f"air freight {rfq['origin']} to {rfq['destination']}"
    goods = rfq["commodity"] or "general cargo"
    dg = "dangerous goods" if rfq["dangerous_goods"] else "no dangerous goods"
    return (
        f"Hello,\n\n"
        f"could you send us your best offer for this shipment?\n\n"
        f"Service: {service}\n"
        f"Ready: {rfq['ready_date'] or 'now'}\n"
        f"Pieces: {_pieces(rfq)}\n"
        f"Goods: {goods}, {dg}\n\n"
        f"Please reply with your all-in price, transit time and rate ID, like this:\n"
        f"Total: 1234.00 EUR\nTransit: 2 days\nRate ID: ABC123\n\n"
        f"Thanks a lot,\nYour air freight team"
    )


def quote_text(rfq: dict, option: dict) -> str:
    # The mail states exactly one amount, the all-in total: a breakdown would add more numbers for the scorer to misread.
    ref = f" ({rfq['customer_reference']})" if rfq.get("customer_reference") else ""
    pieces = sum(p["count"] for p in rfq["pieces"])
    route = f"{rfq['origin']} to {rfq['destination']}"
    pickup = " including pickup at your address" if rfq.get("pickup") else ""
    transit = f", about {option['transit_days']} days in transit" if option.get("transit_days") else ""
    return (
        f"Hello,\n\n"
        f"thanks for your request{ref}. For your {pieces} piece{'s' if pieces != 1 else ''} from {route}{pickup}, "
        f"the {rfq['ask']} option we found is with {option['carrier']}{transit}.\n\n"
        f"All-in price: {option['currency']} {option['total']:,.2f}\n\n"
        f"Just reply to this email and we'll book it for you right away.\n\n"
        f"Best regards,\nYour air freight team"
    )
