"""Tests for src/harvester/email_capture.py.

Focused on the pure-Python helpers — parsing, heuristics, domain
extraction, dedupe key derivation. The IMAP/POP3 transport methods
are exercised in dealflow's upstream test suite where the same logic
originated and aren't re-mocked here.
"""
import os
from email import message_from_bytes, policy
from unittest.mock import patch

import pytest

from src.harvester.email_capture import (
    EmailCapture,
    GENERIC_SENDER_DOMAINS,
    _RawEmail,
)


@pytest.fixture
def cap(tmp_path) -> EmailCapture:
    """Capture with a unique tmp seen-ids file so tests don't bleed."""
    return EmailCapture(
        email="me@example.com",
        password="dummy",
        seen_ids_path=str(tmp_path / ".seen"),
    )


# ─── configured property ─────────────────────────────────────────────


def test_configured_requires_email_and_password(tmp_path):
    """Both creds must be present for capture to attempt a poll."""
    seen = str(tmp_path / ".seen")
    assert EmailCapture(email="", password="", seen_ids_path=seen).configured is False
    assert EmailCapture(email="me", password="", seen_ids_path=seen).configured is False
    assert EmailCapture(email="", password="x", seen_ids_path=seen).configured is False
    assert EmailCapture(email="me", password="x", seen_ids_path=seen).configured is True


def test_capture_returns_empty_when_unconfigured(tmp_path):
    cap = EmailCapture(email="", password="", seen_ids_path=str(tmp_path / ".seen"))
    assert cap.capture_new_emails() == []


def test_init_reads_env_when_args_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_USER", "env@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "env-pass")
    cap = EmailCapture(seen_ids_path=str(tmp_path / ".seen"))
    assert cap.email == "env@example.com"
    assert cap.password == "env-pass"
    assert cap.configured is True


# ─── _looks_like_deal_email ──────────────────────────────────────────


class TestLooksLikeDealEmail:
    def test_pitch_deck_in_subject_passes(self, cap):
        assert cap._looks_like_deal_email("Pitch Deck - Acme AI", "Hi,\n\n") is True

    def test_raising_in_body_passes(self, cap):
        assert cap._looks_like_deal_email(
            "Hello", "We are raising a $5M seed round."
        ) is True

    def test_structured_field_passes(self, cap):
        # 'Website:' pattern alone is enough — common in founder template
        assert cap._looks_like_deal_email(
            "Catch up", "Company: Acme\nWebsite: acme.ai\nStage: Series A"
        ) is True

    def test_normal_email_rejected(self, cap):
        assert cap._looks_like_deal_email(
            "Lunch tomorrow?", "Want to grab lunch around noon?"
        ) is False

    def test_newsletter_rejected(self, cap):
        # No structured fields, no funding keywords in subject
        assert cap._looks_like_deal_email(
            "Weekly Digest #42",
            "Top stories this week: AI gets weirder, ...",
        ) is False


# ─── _extract_sender_address / _extract_sender_domain ───────────────


@pytest.mark.parametrize(
    "from_addr,expected_addr,expected_domain",
    [
        ('"Alice" <alice@acme.ai>', "alice@acme.ai", "acme.ai"),
        ("bob@startup.io", "bob@startup.io", "startup.io"),
        ("Plain Name <c@d.com>", "c@d.com", "d.com"),
        ("noreply@gmail.com", "noreply@gmail.com", "gmail.com"),
        ("", "", ""),
    ],
)
def test_sender_address_and_domain_extraction(
    from_addr, expected_addr, expected_domain
):
    assert EmailCapture._extract_sender_address(from_addr) == expected_addr
    assert EmailCapture._extract_sender_domain(from_addr) == expected_domain


def test_generic_domains_are_recognized():
    """Generic webmail domains must not be used as company-name source."""
    assert "gmail.com" in GENERIC_SENDER_DOMAINS
    assert "yahoo.com" in GENERIC_SENDER_DOMAINS
    assert "outlook.com" in GENERIC_SENDER_DOMAINS
    assert "acme.ai" not in GENERIC_SENDER_DOMAINS


# ─── _extract_company_name ───────────────────────────────────────────


class TestExtractCompanyName:
    def test_pitch_deck_subject_pattern(self):
        name = EmailCapture._extract_company_name(
            "Pitch Deck - Acme AI", "", "founder@acme.ai"
        )
        assert name == "Acme AI"

    def test_intro_subject_pattern(self):
        name = EmailCapture._extract_company_name(
            "Introduction - Stables Money", "", "founder@stables.money"
        )
        assert name == "Stables Money"

    def test_company_field_in_body(self):
        name = EmailCapture._extract_company_name(
            "Catch up",
            "Company: PlasmaLeap\nStage: Series A",
            "alice@plasmaleap.com",
        )
        assert name == "PlasmaLeap"

    def test_sender_domain_fallback(self):
        # No explicit markers — derive from non-generic sender domain
        name = EmailCapture._extract_company_name(
            "Hello", "Just wanted to introduce ourselves.",
            "founder@newco.io",
        )
        assert name == "Newco"

    def test_generic_sender_yields_unknown(self):
        # gmail.com isn't a company — must not be used
        name = EmailCapture._extract_company_name(
            "Hello",
            "Just wanted to introduce ourselves.",
            "person@gmail.com",
        )
        assert name == "Unknown"

    def test_no_clue_yields_unknown(self):
        name = EmailCapture._extract_company_name("Hi", "Hi", "")
        assert name == "Unknown"


# ─── _extract_domain ─────────────────────────────────────────────────


class TestExtractDomain:
    def test_url_in_body_preferred(self):
        d = EmailCapture._extract_domain(
            "Check out our site: https://acme.ai/about",
            "founder@otherbrand.com",
        )
        assert d == "https://acme.ai"

    def test_strips_www_prefix(self):
        d = EmailCapture._extract_domain(
            "Visit https://www.acme.ai",
            "founder@otherbrand.com",
        )
        assert d == "https://acme.ai"

    def test_skips_linkedin_and_other_socials(self):
        # The first non-blocked URL should win, not the LinkedIn one
        d = EmailCapture._extract_domain(
            "Find me on https://linkedin.com/in/foo or visit https://realstartup.io",
            "x@x.com",
        )
        assert d == "https://realstartup.io"

    def test_falls_back_to_sender_domain(self):
        d = EmailCapture._extract_domain(
            "Just saying hi — no links here.",
            "founder@newco.io",
        )
        assert d == "https://newco.io"

    def test_returns_none_when_only_generic_sender(self):
        # No body URL + sender is gmail — nothing to bind to
        d = EmailCapture._extract_domain("Just hi.", "alice@gmail.com")
        assert d is None

    def test_skips_cdn_and_tracker_domains(self):
        d = EmailCapture._extract_domain(
            "Image: https://googleusercontent.com/x.png",
            "alice@gmail.com",
        )
        assert d is None


# ─── _parse_to_company ───────────────────────────────────────────────


def _raw(subject, body, from_addr, attachments=None):
    return _RawEmail(
        subject=subject,
        from_addr=from_addr,
        body=body,
        attachments=attachments or [],
        message_id="<msg-1@x>",
        date="Fri, 17 May 2026 12:00:00 +1000",
    )


class TestParseToCompany:
    def test_full_deal_email_yields_company(self, cap):
        raw = _raw(
            "Pitch Deck - Acme AI",
            "Acme builds large-scale model infra. Visit https://acme.ai.",
            "founder@acme.ai",
            attachments=["deck.pdf"],
        )
        out = cap._parse_to_company(raw)
        assert out is not None
        assert out["company_name"] == "Acme AI"
        assert out["domain"] == "https://acme.ai"
        assert out["vc_source"] == "Email"
        assert out["source_email"] == "founder@acme.ai"
        assert out["source_url"] == "mailto:founder@acme.ai"
        assert out["attachment_filenames"] == ["deck.pdf"]
        assert out["captured_at"]  # ISO timestamp present

    def test_non_deal_email_returns_none(self, cap):
        raw = _raw(
            "Lunch?",
            "Want to grab lunch tomorrow?",
            "alice@gmail.com",
        )
        assert cap._parse_to_company(raw) is None

    def test_unknown_company_dropped_early(self, cap):
        # 'Raising' triggers _looks_like_deal_email, but no name/domain clues
        raw = _raw(
            "Raising again",
            "We are raising a new round. Reply to chat!",
            "noreply@gmail.com",
        )
        assert cap._parse_to_company(raw) is None

    def test_missing_domain_yields_none(self, cap):
        # Generic sender + no URL in body = no domain → drop
        raw = _raw(
            "Pitch Deck - Acme AI",
            "Pitch attached. Series A in progress.",
            "alice@gmail.com",
        )
        assert cap._parse_to_company(raw) is None


# ─── _html_to_text ───────────────────────────────────────────────────


class TestHtmlToText:
    def test_strips_script_and_style(self, cap):
        out = cap._html_to_text(
            "<p>Hello</p><script>alert(1)</script><style>p{}</style><p>World</p>"
        )
        assert "alert" not in out
        assert "p{}" not in out
        assert "Hello" in out and "World" in out

    def test_decodes_html_entities(self, cap):
        out = cap._html_to_text("<p>Tom &amp; Jerry &mdash; partners</p>")
        assert "Tom & Jerry" in out

    def test_collapses_whitespace(self, cap):
        out = cap._html_to_text("<p>a</p>\n\n   \t  <p>b</p>")
        assert "a b" in out


# ─── _stable_message_key ─────────────────────────────────────────────


def _build_parsed(headers: dict[str, str], body: str = ""):
    raw_bytes = (
        "\r\n".join(f"{k}: {v}" for k, v in headers.items())
        + "\r\n\r\n"
        + body
    ).encode("utf-8")
    return message_from_bytes(raw_bytes, policy=policy.default)


class TestStableMessageKey:
    def test_message_id_preferred(self, cap):
        parsed = _build_parsed(
            {"Message-ID": "<abc@x>", "From": "a@b.c", "Subject": "Hi"}
        )
        key = cap._stable_message_key(parsed, "body")
        assert key == "msgid:abc@x"

    def test_hash_fallback_when_no_message_id(self, cap):
        parsed = _build_parsed(
            {"From": "a@b.c", "Subject": "Hi", "Date": "Fri"}
        )
        key = cap._stable_message_key(parsed, "some body text")
        assert key.startswith("hash:")
        # Same input twice → same key (deterministic)
        assert key == cap._stable_message_key(parsed, "some body text")

    def test_different_bodies_produce_different_keys(self, cap):
        parsed = _build_parsed(
            {"From": "a@b.c", "Subject": "Hi", "Date": "Fri"}
        )
        k1 = cap._stable_message_key(parsed, "body one")
        k2 = cap._stable_message_key(parsed, "body two")
        assert k1 != k2


# ─── Seen-IDs persistence ────────────────────────────────────────────


class TestSeenIds:
    def test_load_returns_empty_when_file_missing(self, tmp_path):
        cap = EmailCapture(
            email="a", password="b",
            seen_ids_path=str(tmp_path / "missing.txt"),
        )
        assert cap._seen_ids == set()

    def test_round_trip_persists_ids(self, tmp_path):
        path = tmp_path / ".seen"
        cap = EmailCapture(email="a", password="b", seen_ids_path=str(path))
        cap._seen_ids.update({"msgid:a", "msgid:b", "msgid:c"})
        cap._save_seen_ids()
        cap2 = EmailCapture(email="a", password="b", seen_ids_path=str(path))
        assert cap2._seen_ids == {"msgid:a", "msgid:b", "msgid:c"}

    def test_bounded_at_50k(self, tmp_path):
        path = tmp_path / ".seen"
        cap = EmailCapture(email="a", password="b", seen_ids_path=str(path))
        cap._seen_ids = {f"msgid:{i}" for i in range(50_500)}
        cap._save_seen_ids()
        cap2 = EmailCapture(email="a", password="b", seen_ids_path=str(path))
        assert len(cap2._seen_ids) == 50_000
