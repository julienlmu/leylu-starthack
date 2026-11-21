"""A password written in the mail body reaches the backend's attachment reader (encrypted zip / PDF)."""
import pytest

import rfq_agent


@pytest.mark.parametrize("body,hint", [
    ("The zip is protected, password: Fr8-2026.", "Fr8-2026"),
    ("Passwort: geheim42", "geheim42"),
    ("mot de passe : Lyon#99", "Lyon#99"),
    ("pw: abc123", "abc123"),
    ('The password is "S3cret!"', "S3cret!"),
    ("Kennwort lautet X7y8", "X7y8"),
])
def test_hints_from_the_body(body, hint):
    assert hint in rfq_agent.password_hints(body)


def test_no_password_no_hints_and_no_extra_argument():
    assert rfq_agent.password_hints("Please quote 3 pallets FRA-JFK, 450 kg.") == []
    calls = []

    class Box:
        def attachment(self, mail, attachment):
            return b"PK"

    class Api:
        def attachment_text(self, name, content_b64, **kwargs):
            calls.append(kwargs)
            return "UN3480"

    rfq_agent._attachment_texts(1, {"body": "no secrets here", "attachments": [{"filename": "a.zip"}]}, Box(), Api())
    rfq_agent._attachment_texts(1, {"body": "Passwort: pw1", "attachments": [{"filename": "a.zip"}]}, Box(), Api())
    assert calls == [{}, {"password_hints": ["pw1"]}]
