# "Please confirm …" is not a booking (review)
- Who: Orhun
- Branch: orhun/confirm-accept
- What changed: agent/booking_agent.py ACCEPT: "confirm" counts as a yes only in "I/we (hereby) confirm" or "confirm the/our booking|order|offer|quote" (DE: "ich/wir bestätige…", "bestätigen die Buchung/den Auftrag"); "Please confirm you can do 3 pallets", "please confirm pickup on Monday", "please confirm receipt" no longer book.
- How verified: agent 1312 passed (3 review sentences + German receipt sentence are not a yes; "We confirm the booking" and "I confirm the order" are)
