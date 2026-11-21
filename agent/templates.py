"""Customer mail templates. Written by hand, not by the LLM (cost), and meant to read human.

shortcut: English placeholder wording; task U4 (Ulas) replaces it with the final templates and languages.
"""


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
