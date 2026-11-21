"""Links in an RFQ (links.py): read like attachments, unsafe sites never opened, no browser so no popups. Offline:
a fake web (httpx.MockTransport) and a fake DNS."""
import httpx

import links

PUBLIC = lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))]
PRIVATE = lambda host, port: [(2, 1, 6, "", ("10.0.0.5", 0))]


def web(pages: dict):
    def handle(request):
        page = pages.get(str(request.url))
        if page is None:
            return httpx.Response(404)
        status, headers, body = page
        return httpx.Response(status, headers=headers, content=body)
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_find_links():
    text = "Packing list: https://files.example.com/pl.pdf. Details at www.shipper.example/rfq, thanks"
    assert links.find(text) == ["https://files.example.com/pl.pdf", "https://www.shipper.example/rfq"]


def test_share_links_become_downloads():
    assert links.direct("https://drive.google.com/file/d/AbC_1/view?usp=sharing") == \
        "https://drive.google.com/uc?export=download&id=AbC_1"
    assert links.direct("https://www.dropbox.com/s/x/pl.xlsx?dl=0") == "https://www.dropbox.com/s/x/pl.xlsx?dl=1"
    assert links.direct("https://docs.google.com/spreadsheets/d/K9/edit#gid=0") == \
        "https://docs.google.com/spreadsheets/d/K9/export?format=xlsx"


def test_unsafe_links_are_never_opened():
    cases = {"ftp://files.example.com/pl.pdf": "scheme", "https://paypal.com@evil.example/x": "phishing",
             "https://files.example.com:8443/pl.pdf": "port", "http://192.168.1.10/pl.pdf": "IP",
             "https://xn--pypal-4ve.com/pl.pdf": "look-alike", "https://files.example.com/invoice.exe": "program",
             "https://localhost/pl.pdf": "host"}
    for url, why in cases.items():
        assert why in (links.unsafe(url, PUBLIC) or ""), url
    assert "public" in links.unsafe("https://intranet.example.com/pl.pdf", PRIVATE)  # resolves into a LAN
    assert links.unsafe("https://files.example.com/pl.pdf", PUBLIC) is None


def test_a_redirect_into_the_lan_is_stopped():
    resolve = lambda host, port: PRIVATE(host, port) if host == "internal.example" else PUBLIC(host, port)
    client = web({"https://bit.example/x": (302, {"location": "http://internal.example/admin"}, b"")})
    try:
        links.fetch("https://bit.example/x", client, resolve)
        raise AssertionError("opened")
    except ValueError as error:
        assert "public" in str(error)


def test_programs_logins_and_big_files_are_refused():
    client = web({
        "https://a.example/f": (200, {"content-type": "application/x-msdownload"}, b"MZ"),
        "https://a.example/g": (200, {"content-type": "application/octet-stream",
                                      "content-disposition": 'attachment; filename="pl.pdf.exe"'}, b"MZ"),
        "https://a.example/login": (200, {"content-type": "text/html"},
                                    b'<form><input type="password" name="p"></form>'),
        "https://a.example/big": (200, {"content-type": "application/pdf"}, b"%PDF" + b"0" * (links.MAX_BYTES + 1)),
    })
    for path, why in {"f": "not a document", "g": "program", "login": "login", "big": "8 MB"}.items():
        try:
            links.fetch(f"https://a.example/{path}", client, PUBLIC)
            raise AssertionError(path)
        except ValueError as error:
            assert why in str(error), (path, error)


def test_popups_scripts_and_cookie_walls_are_cut_out_of_a_page():
    page = ("<html><head><script>alert('x');window.open('https://ads.example')</script><style>.m{}</style></head><body>"
            "<div class='cookie-banner'><p>We use cookies. <b>Accept all</b></p></div>"
            "<div id='newsletter-modal' class='modal'><div><p>Subscribe for 10% off!</p></div></div>"
            "<dialog open>Win a prize</dialog><iframe src='https://ads.example'></iframe>"
            "<h1>Shipment</h1><table><tr><td>3 pallets</td><td>640 kg</td></tr></table><p>UN 3480 lithium</p></body></html>")
    client = web({"https://shipper.example/rfq": (200, {"content-type": "text/html; charset=utf-8"}, page.encode())})
    name, data = links.fetch("https://shipper.example/rfq", client, PUBLIC)
    text = data.decode()
    assert name == "rfq.txt"
    assert "640 kg" in text and "UN 3480" in text
    for gone in ("alert", "window.open", "cookies", "Subscribe", "Win a prize", "iframe"):
        assert gone not in text, gone


def test_read_all_feeds_the_attachment_reader_and_logs_every_link():
    client = web({"https://files.example.com/pl.csv": (200, {"content-type": "text/csv"}, b"pieces,kg\n3,640\n"),
                  "https://drive.google.com/uc?export=download&id=Z": (302, {"location": "https://files.example.com/pl.csv"}, b"")})
    got = links.read_all("see https://drive.google.com/file/d/Z/view and https://files.example.com/x.exe",
                         lambda name, data: f"{name}:{data.decode()}", client, PUBLIC)
    assert got[0][1] == "pl.csv:pieces,kg\n3,640\n" and got[0][2].startswith("read as pl.csv")
    assert got[1][1] == "" and "program" in got[1][2]


def test_an_rfq_whose_facts_sit_behind_a_link_is_quoted(tmp_path, monkeypatch):
    import re
    import extract as extract_mod
    import rfq_agent
    from inbox import FixtureMailbox
    from test_rfq_agent import FakeApi, OPTION, RAW
    client = web({"https://shipper.example/pl.csv": (200, {"content-type": "text/csv"},
                                                       b"pieces,weight kg,cargo\n3,640,lithium batteries UN 3480\n")})
    real = links.read_all
    monkeypatch.setattr(links, "read_all", lambda text, to_text: real(text, to_text, client, PUBLIC))
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    seen = []

    class Api(FakeApi):
        def attachment_text(self, name, content_base64, **hints):
            import base64
            seen.append(name)
            return base64.b64decode(content_base64).decode()

        def event(self, session_id, kind, text, data=None, cost=0.0):
            super().event(session_id, kind, text, data, cost)
            seen.append(text)

    box, api = FixtureMailbox(tmp_path), Api({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    mail = {"id": "m1", "thread_id": "t1", "from": "buyer@customer.example", "subject": "RFQ MUC-JFK",
            "body": "Please quote MUC to JFK, packing list here: https://shipper.example/pl.csv"}
    rfq_agent.handle_rfq(mail, box, api)
    assert "pl.csv" in seen and any(t.startswith("Link https://shipper.example/pl.csv read as pl.csv") for t in seen)
    assert any("Dangerous goods found" in t for t in seen if isinstance(t, str))  # the DG behind the link counts
    assert len(box.sent) == 1 and re.search(r"UN ?3480|dangerous|MSDS", box.sent[0]["body"], re.I)
