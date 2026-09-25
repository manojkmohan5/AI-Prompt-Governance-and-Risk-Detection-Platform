"""
Credentials in prompts and answers: detected, and masked before the LLM.

Only a handful of API-key prefixes were recognised. A password in pasted code,
the password in a connection string, a private key or a bearer token went
straight through - and even a recognised key was not masked when a prompt was
redacted, because redaction covered personal data only.
"""
import pytest

from app.governance import entities as ent
from app.governance import inspector as insp
from app.governance import response_inspector as ri


def _secrets(text):
    return [(e.type, e.value) for e in ent.extract_identifiers(text) if e.type in ent.SECRET_TYPES]


@pytest.mark.parametrize("text, expected", [
    ("db.connect(host='prod-db.internal', user='admin', password='Sup3rS3cr3t!')",
     ("PASSWORD", "Sup3rS3cr3t!")),
    ("DATABASE_URL=postgres://admin:Sup3rS3cr3t@db.internal:5432/app",
     ("PASSWORD", "Sup3rS3cr3t")),
    ("pwd: hunter2hunter2", ("PASSWORD", "hunter2hunter2")),
    ('config = {"client_secret": "a8Kd02mQvX71pLs"}', ("PASSWORD", "a8Kd02mQvX71pLs")),
    ("requests.get(url, headers={'Authorization': 'Bearer ghx7Rk2mNvQ4rTb8XwZc3Lp6Yt9A'})",
     ("TOKEN", "ghx7Rk2mNvQ4rTb8XwZc3Lp6Yt9A")),
    ("api_key = 'q9T4xLm2Vb7Rk3Wz'", ("API_KEY", "q9T4xLm2Vb7Rk3Wz")),
    ("access_token: 7fG2kLq9Xm4Rt8Vb", ("API_KEY", "7fG2kLq9Xm4Rt8Vb")),
])
def test_credentials_in_code_and_config_are_found(text, expected):
    assert expected in _secrets(text)


def test_a_jwt_is_found_on_its_own():
    jwt = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
           "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
    assert ("TOKEN", jwt) in _secrets(f"why is this token rejected? {jwt}")


def test_a_private_key_block_is_one_entity():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7abcdef\n-----END RSA PRIVATE KEY-----"
    assert _secrets(f"here is the key:\n{pem}\nthanks") == [("PRIVATE_KEY", pem)]


@pytest.mark.parametrize("text", [
    "I forgot my password, how do I reset it?",
    "Please reset my password: I forgot it",      # value too short to be one
    "password = ${DB_PASSWORD}",                  # a reference, not a secret
    "api_key: <your key here>",
    "Explain how bearer tokens work in OAuth",
])
def test_talking_about_credentials_is_not_a_credential(text):
    assert _secrets(text) == []


def test_the_password_in_a_connection_string_is_not_read_as_an_email():
    types = [e.type for e in ent.extract_identifiers("postgres://admin:Sup3rS3cr3t@db.example.com/app")]
    assert "PASSWORD" in types and "EMAIL" not in types


def test_a_credential_raises_sensitive_data():
    result = insp.inspector.inspect("db.connect(user='admin', password='Sup3rS3cr3t!')")
    assert "SENSITIVE_DATA" in result.flags


def test_redaction_masks_the_value_and_keeps_the_code_readable():
    text = "db.connect(user='admin', password='Sup3rS3cr3t!')"
    masked = ent.redact(text, [e for e in ent.extract_identifiers(text) if e.type in ent.SECRET_TYPES])
    assert masked == "db.connect(user='admin', password='[PASSWORD_REDACTED]')"


def test_a_credential_in_an_answer_is_masked_before_delivery(monkeypatch):
    monkeypatch.setattr(ent, "ner_available", lambda: False)
    answer = "Connect with postgres://admin:Sup3rS3cr3t@db.internal/app and retry."
    result = ri.inspect_response(answer)
    assert result.secrets_detected
    delivered = ri.redact_response(answer, result)
    assert "Sup3rS3cr3t" not in delivered and "and retry" in delivered
