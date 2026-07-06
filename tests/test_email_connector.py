"""Test the email connector — pure logic only, no IMAP/network."""
import email as email_lib

import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    import src.modules.email_connector as ec
    monkeypatch.setattr(ec, "ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setattr(ec, "SEEN_FILE", str(tmp_path / "email" / "seen.json"))
    monkeypatch.setattr(ec, "DATA_DIR", str(tmp_path))
    yield tmp_path


RECRUITS = {"names": {"jane smith", "mike torres"}, "emails": {"jane@gmail.com"}}
CLIENTS = {"names": {"barry porter", "vivian walker"}}


def test_split_sender():
    from src.modules.email_connector import split_sender
    assert split_sender('"Mutual of Omaha" <newbiz@mutualofomaha.com>') == \
        ("Mutual of Omaha", "newbiz@mutualofomaha.com")
    assert split_sender("plain@example.com") == ("", "plain@example.com")
    assert split_sender("Jane Smith <jane@gmail.com>") == ("Jane Smith", "jane@gmail.com")


def test_classify_carrier_urgent_vs_info():
    from src.modules.email_connector import classify_email
    urgent = classify_email("Underwriting <uw@mutualofomaha.com>",
                            "Outstanding requirement on your case", "Please submit APS",
                            RECRUITS, CLIENTS)
    assert urgent["category"] == "carrier" and urgent["priority"] == "high"
    info = classify_email("AIG <svc@corebridge.com>", "Policy issued", "Congrats",
                          RECRUITS, CLIENTS)
    assert info["category"] == "carrier" and info["priority"] == "medium"


def test_classify_recruit_by_email_and_name():
    from src.modules.email_connector import classify_email
    by_email = classify_email("Jane <jane@gmail.com>", "Re: opportunity", "interested!",
                              RECRUITS, CLIENTS)
    assert by_email["category"] == "recruit"
    by_name = classify_email("Mike Torres <mike.t@yahoo.com>", "call me", "",
                             RECRUITS, CLIENTS)
    assert by_name["category"] == "recruit"
    assert by_name["matched"].lower() == "mike torres"


def test_classify_client_and_other():
    from src.modules.email_connector import classify_email
    client = classify_email("Barry Porter <bporter@aol.com>", "question about my policy", "",
                            RECRUITS, CLIENTS)
    assert client["category"] == "client"
    other = classify_email("Newsletter <news@randomsite.com>", "Weekly deals", "buy now",
                           RECRUITS, CLIENTS)
    assert other["category"] == "other"


def test_carrier_beats_client_when_both_match():
    from src.modules.email_connector import classify_email
    # carrier token present and a client name in subject — carrier wins
    res = classify_email("Mutual of Omaha <uw@omaha.com>", "Barry Porter requirement", "",
                         RECRUITS, CLIENTS)
    assert res["category"] == "carrier"


def test_build_email_items_dedup_and_digest():
    from src.modules.email_connector import build_email_items
    messages = [
        {"from": "Underwriting <uw@mutualofomaha.com>", "subject": "Requirement needed",
         "body": "send APS", "date": "Fri, 13 Jun 2026 09:00:00", "message_id": "<a@x>"},
        {"from": "Jane <jane@gmail.com>", "subject": "I'm interested", "body": "lets talk",
         "date": "Fri, 13 Jun 2026 10:00:00", "message_id": "<b@x>"},
        {"from": "News <news@site.com>", "subject": "Sale", "body": "buy",
         "date": "Fri, 13 Jun 2026 11:00:00", "message_id": "<c@x>"},
    ]
    tasks, digest, seen = build_email_items(messages, RECRUITS, CLIENTS, set())
    assert len(tasks) == 2                      # carrier + recruit, not newsletter
    assert len(digest) == 3                     # everything in digest
    titles = " ".join(t["title"] for t in tasks)
    assert "Carrier email" in titles and "recruit Jane" in titles
    # re-run with the seen set: no new tasks, digest still regenerates
    tasks2, digest2, seen2 = build_email_items(messages, RECRUITS, CLIENTS, seen)
    assert tasks2 == []
    assert len(digest2) == 3


def test_email_task_keys_are_stable():
    from src.modules.email_connector import build_email_items
    msg = [{"from": "UW <uw@aig.com>", "subject": "Declined", "body": "",
            "date": "x", "message_id": "<stable@id>"}]
    k1 = build_email_items(msg, RECRUITS, CLIENTS, set())[0][0]["key"]
    k2 = build_email_items(msg, RECRUITS, CLIENTS, set())[0][0]["key"]
    assert k1 == k2 and k1.startswith("email-")


def test_account_env_round_trip(isolated):
    from src.modules.email_connector import save_email_account, load_email_accounts
    save_email_account("gmail", "joe@gmail.com", "app-pass-1")
    save_email_account("outlook", "joe@work.com", "app|pass|2")  # password with pipes
    accts = load_email_accounts()
    assert len(accts) == 2
    assert accts[0]["host"] == "imap.gmail.com"
    assert accts[1]["address"] == "joe@work.com"
    assert accts[1]["password"] == "app|pass|2"
    assert accts[1]["host"] == "outlook.office365.com"


def test_imap_from_mx_mapping():
    from src.modules.email_connector import _imap_from_mx
    assert _imap_from_mx("aspmx.l.google.com") == "imap.gmail.com"
    assert _imap_from_mx("example-org.mail.protection.outlook.com") == "outlook.office365.com"
    assert _imap_from_mx("smtp.secureserver.net") == "imap.secureserver.net"
    assert _imap_from_mx("mx.zoho.com") == "imap.zoho.com"
    assert _imap_from_mx("unknown-host.example.com") == ""


def test_detect_imap_host_consumer():
    from src.modules.email_connector import detect_imap_host
    assert detect_imap_host("example.user@hotmail.com") == "outlook.office365.com"
    assert detect_imap_host("someone@gmail.com") == "imap.gmail.com"


def test_explicit_host_round_trip(isolated):
    from src.modules.email_connector import save_email_account, load_email_accounts
    save_email_account("custom", "joe@example-agency.org", "secretpass",
                       host="outlook.office365.com")
    acct = load_email_accounts()[0]
    assert acct["address"] == "joe@example-agency.org"
    assert acct["host"] == "outlook.office365.com"
    assert acct["password"] == "secretpass"


def test_legacy_three_field_account(isolated):
    """Accounts saved before the host field still load."""
    (isolated / ".env").write_text("EMAIL_ACCOUNT_1=gmail|old@gmail.com|legacypass\n")
    acct = load_email_accounts_reload()
    assert acct["host"] == "imap.gmail.com"
    assert acct["password"] == "legacypass"


def load_email_accounts_reload():
    from src.modules.email_connector import load_email_accounts
    return load_email_accounts()[0]


def test_parse_message_plaintext():
    from src.modules.email_connector import parse_message
    raw = ("From: Underwriting <uw@mutualofomaha.com>\r\n"
           "Subject: Requirement needed\r\n"
           "Date: Fri, 13 Jun 2026 09:00:00 -0500\r\n"
           "Message-ID: <abc@omaha>\r\n"
           "Content-Type: text/plain; charset=utf-8\r\n\r\n"
           "Please submit the APS for this client.\r\n")
    msg = parse_message(email_lib.message_from_string(raw))
    assert msg["from"] == "Underwriting <uw@mutualofomaha.com>"
    assert msg["subject"] == "Requirement needed"
    assert "APS" in msg["body"]
    assert msg["message_id"] == "<abc@omaha>"


def test_run_email_connector_no_accounts(isolated):
    from src.modules.email_connector import run_email_connector
    res = run_email_connector()
    assert res == {"tasks": [], "digest": [], "accounts": 0, "errors": []}
