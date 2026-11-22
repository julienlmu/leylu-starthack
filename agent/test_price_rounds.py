"""Live rounds that lost price points (postmortem docs/postmortem/sessions_r85_r91.json on orhun/postmortem-r85-r91)."""
import shapes

R89 = ("Hi there,\n\nHope your week's going well! Could you quote the fastest air freight option for each of these two "
       "shipments? Both will be ready for pickup on 2026-11-23 at our site in Wiesbaden, Germany (postcode 65996). Please "
       "arrange the truck from our site to the airport as part of the quote.\n\n1. GRU (Sao Paulo, BR) - automotive "
       "sensors, 4 pieces, gross weight 1281 kg, volume 3.76 cbm.\n2. TLV (Tel Aviv, IL) - machine parts, 1 piece, gross "
       "weight 1812 kg, volume 5.75 cbm.\n\nCould you send both quotes in the same reply, with a separate all-in price in "
       "EUR for each shipment rather than a combined total?\n\nThanks for your help!\n\nPetra Hofmann")



def test_r89_separate_prices_rather_than_a_combined_total_is_not_one_total():
    assert not shapes._one_total(R89)
    assert shapes._one_total("Please give us one total for both shipments.")
    assert shapes._one_total("We need a combined price for both lots.")
