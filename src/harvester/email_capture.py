"""Email-based harvester input.

Adapted from dealflow's CaptureAgent. Where dealflow built a Deal
object with headquarters/funding_stage extracted via regex (dealflow
needed those for its Gatekeeper), this version produces raw company
dicts in dealradar's harvester shape so the reasoner pipeline can
treat email-sourced and VC-portfolio-sourced companies uniformly.

Key adaptations from the upstream:
- Output dict shape matches HarvesterPipeline output:
    {company_name, domain, vc_source, source_url, source_email, captured_at}
- HQ/stage extraction dropped — dealradar's reasoner derives those
  from the live website + LLM, not from the inbound email.
- Attachment bodies are NOT persisted (dealradar has no file-storage
  path yet); only filenames are noted in source_url for traceability.
- Imports are local so calling code that doesn't need email capture
  doesn't pay the imaplib/poplib import cost.

Environment variables consumed (all optional; absence disables capture):
    EMAIL_USER         — full inbox address
    EMAIL_PASSWORD     — IMAP/POP3 app password
    EMAIL_PROTOCOL     — 'auto' | 'imap' | 'pop3' (default 'auto')
    IMAP_HOST/IMAP_PORT — defaults imap.gmail.com:993
    POP_HOST/POP_PORT  — defaults pop.gmail.com:995
    EMAIL_MAX_MESSAGES — default 200 (most-recent N messages scanned)
    CAPTURE_SEEN_IDS_PATH — default '.email_capture_seen_ids'
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.header import decode_header
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


STAGE_HINT_KEYWORDS = (
    "pitch deck",
    "investment opportunity",
    "fundraising",
    "raising",
    "series ",
    "pre-ipo",
    "pre ipo",
    "seed round",
    "introduction to",
    "intro to",
)

GENERIC_SENDER_DOMAINS = frozenset(
    {
        "gmail.com",
        "outlook.com",
        "hotmail.com",
        "yahoo.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
        "qq.com",
        "163.com",
        "126.com",
    }
)


@dataclass
class _RawEmail:
    """Internal representation of a fetched message."""

    subject: str
    from_addr: str
    body: str
    attachments: list[dict]
    message_id: str
    date: str


class EmailCapture:
    """Pulls deal emails from an IMAP or POP3 inbox and converts them
    to raw company dicts. Stateful via a seen-IDs file so re-polls
    don't re-emit the same email.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        protocol: str = "auto",
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
        imap_timeout_sec: int = 30,
        pop_host: str = "pop.gmail.com",
        pop_port: int = 995,
        max_messages: int = 200,
        seen_ids_path: Optional[str] = None,
    ):
        self.email = email or os.getenv("EMAIL_USER", "")
        self.password = password or os.getenv("EMAIL_PASSWORD", "")
        self.protocol = (
            protocol or os.getenv("EMAIL_PROTOCOL", "auto")
        ).strip().lower()
        self.imap_host = imap_host or os.getenv("IMAP_HOST", "imap.gmail.com")
        self.imap_port = int(os.getenv("IMAP_PORT", str(imap_port)))
        self.imap_timeout_sec = max(5, int(imap_timeout_sec))
        self.pop_host = pop_host or os.getenv("POP_HOST", "pop.gmail.com")
        self.pop_port = int(os.getenv("POP_PORT", str(pop_port)))
        self.max_messages = max(
            1, int(os.getenv("EMAIL_MAX_MESSAGES", str(max_messages)))
        )
        self._seen_ids_path = Path(
            seen_ids_path
            or os.getenv("CAPTURE_SEEN_IDS_PATH", ".email_capture_seen_ids")
        )
        self._seen_ids = self._load_seen_ids()

    @property
    def configured(self) -> bool:
        """True if there are enough credentials to attempt a poll."""
        return bool(self.email and self.password)

    # ─── Seen-IDs persistence (bounded) ──────────────────────────────

    def _load_seen_ids(self) -> set[str]:
        if not self._seen_ids_path.exists():
            return set()
        try:
            return {
                line.strip()
                for line in self._seen_ids_path.read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()
                if line.strip()
            }
        except OSError:
            return set()

    def _save_seen_ids(self) -> None:
        try:
            self._seen_ids_path.parent.mkdir(parents=True, exist_ok=True)
            ids = list(self._seen_ids)
            if len(ids) > 50000:
                ids = ids[-50000:]
                self._seen_ids = set(ids)
            self._seen_ids_path.write_text("\n".join(ids), encoding="utf-8")
        except OSError:
            pass

    # ─── Header / body decoding ──────────────────────────────────────

    @staticmethod
    def _decode_str(s) -> str:
        if not s:
            return ""
        result = ""
        for part, enc in decode_header(s):
            if isinstance(part, bytes):
                result += part.decode(enc or "utf-8", errors="replace")
            else:
                result += part
        return result

    @staticmethod
    def _html_to_text(html: str) -> str:
        text = re.sub(
            r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_text_body(self, parsed_email) -> str:
        if parsed_email.is_multipart():
            html_fallback = ""
            for part in parsed_email.walk():
                content_type = part.get_content_type()
                if content_type not in ("text/plain", "text/html"):
                    continue
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True) or b""
                content = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    return content
                if content_type == "text/html":
                    html_fallback = self._html_to_text(content)
            return html_fallback

        charset = parsed_email.get_content_charset() or "utf-8"
        payload = parsed_email.get_payload(decode=True)
        if payload is None:
            text = parsed_email.get_payload()
            return text if isinstance(text, str) else ""
        content = payload.decode(charset, errors="replace")
        if parsed_email.get_content_type() == "text/html":
            return self._html_to_text(content)
        return content

    def _list_attachment_names(self, parsed_email) -> list[str]:
        names = []
        if not parsed_email.is_multipart():
            return names
        for part in parsed_email.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = part.get("Content-Disposition") or ""
            if "attachment" not in disposition.lower():
                continue
            filename = part.get_filename()
            if filename:
                names.append(self._decode_str(filename))
        return names

    # ─── Deal-email heuristics ───────────────────────────────────────

    @staticmethod
    def _looks_like_deal_email(subject: str, body: str) -> bool:
        subject_l = subject.lower()
        body_l = body.lower()
        has_signal = any(kw in subject_l for kw in STAGE_HINT_KEYWORDS) or any(
            kw in body_l[:2000] for kw in STAGE_HINT_KEYWORDS
        )
        has_structured = bool(
            re.search(
                r"(?:company|website|hq|headquarters|stage|raising|round)\s*[:\-]",
                body,
                re.IGNORECASE,
            )
        )
        return has_signal or has_structured

    @staticmethod
    def _extract_sender_address(from_addr: str) -> str:
        m = re.search(r"<([^>]+)>", from_addr)
        candidate = m.group(1) if m else from_addr
        return candidate.strip().lower()

    @staticmethod
    def _extract_sender_domain(from_addr: str) -> str:
        addr = EmailCapture._extract_sender_address(from_addr)
        if "@" not in addr:
            return ""
        return addr.rsplit("@", 1)[-1]

    @classmethod
    def _extract_company_name(
        cls, subject: str, body: str, from_addr: str
    ) -> str:
        """Best-effort company name from explicit markers, then a
        sender-domain fallback. Returns 'Unknown' as a last resort —
        the gatekeeper will drop such rows downstream.

        Character class explicitly excludes whitespace other than
        single spaces to keep the match from spanning newlines and
        slurping body text into the name.
        """
        # The class is [A-Za-z0-9 &.-] (literal space, no \s) so the
        # capture stops at end-of-line. \n is also a hard terminator.
        patterns = (
            r"(?:Pitch\s*Deck|Intro(?:duction)?|Investment\s*Opportunity)\s*[-:|]\s*"
            r"([A-Z][A-Za-z0-9 &\.\-]{1,80}?)(?:\s*[-:|]|[\r\n]|$)",
            r"(?:Company|Startup|Venture)\s*[:\-]\s*"
            r"([A-Z][A-Za-z0-9 &\.\-]{1,80}?)(?:[\r\n,]|$)",
        )
        haystack = f"{subject}\n{body[:2000]}"
        for pattern in patterns:
            m = re.search(pattern, haystack, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip(" -|:")
                if candidate and len(candidate) > 2:
                    return candidate

        sender_domain = cls._extract_sender_domain(from_addr)
        if sender_domain and sender_domain not in GENERIC_SENDER_DOMAINS:
            # 'acme.ai' -> 'Acme', 'startupcorp.io' -> 'Startupcorp'
            base = sender_domain.split(".")[0]
            cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", base).strip()
            if cleaned:
                return cleaned.title()
        return "Unknown"

    # Infra / social / CDN / tracker domains that show up in email
    # signatures but are never the startup's primary site.
    _BLOCKED_URL_HOSTS: tuple[str, ...] = (
        "google.com",
        "googleusercontent.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "youtube.com",
        "mailchimp.com",
        "sendgrid.net",
        "amazonaws.com",
        "cloudfront.net",
        "wikipedia.org",
        "github.com",
        "calendly.com",
    )

    @classmethod
    def _extract_domain(cls, body: str, from_addr: str) -> Optional[str]:
        """Walk every URL in the first ~5KB of the body and return the
        first one that isn't on the blocklist (CDN, social, scheduler).
        Founders typically link their site early; the blocklist filters
        the inevitable LinkedIn/calendar/Twitter mentions that often
        come first. Falls back to the sender's domain if no body URL
        survives the filter. Returns a normalized 'https://host' string
        or None.
        """
        for m in re.finditer(
            r"https?://(?P<host>[a-zA-Z0-9][\w\-\.]+\.[a-zA-Z]{2,})(?:/\S*)?",
            body[:5000],
        ):
            host = m.group("host").lower()
            if any(host == b or host.endswith("." + b) for b in cls._BLOCKED_URL_HOSTS):
                continue
            if host.startswith("www."):
                host = host[4:]
            return f"https://{host}"

        sender_domain = cls._extract_sender_domain(from_addr)
        if (
            sender_domain
            and sender_domain not in GENERIC_SENDER_DOMAINS
            and not any(
                sender_domain == b or sender_domain.endswith("." + b)
                for b in cls._BLOCKED_URL_HOSTS
            )
        ):
            return f"https://{sender_domain}"
        return None

    # ─── Message identity (for dedupe across polls) ─────────────────

    def _stable_message_key(self, parsed_email, body: str) -> str:
        message_id = (
            self._decode_str(parsed_email.get("Message-ID", "")).strip().lower()
        )
        if message_id:
            return f"msgid:{message_id.strip('<>')}"
        subject = self._decode_str(parsed_email.get("Subject", "")).strip().lower()
        from_addr = self._decode_str(parsed_email.get("From", "")).strip().lower()
        date_hdr = self._decode_str(parsed_email.get("Date", "")).strip().lower()
        snippet = (body or "").strip().lower()[:4000]
        digest_input = f"{subject}|{from_addr}|{date_hdr}|{snippet}".strip("|")
        if not digest_input:
            return ""
        digest = hashlib.sha1(
            digest_input.encode("utf-8", errors="ignore")
        ).hexdigest()
        return f"hash:{digest}"

    # ─── Email → company dict ────────────────────────────────────────

    def _parse_to_company(self, raw: _RawEmail) -> Optional[dict]:
        if not self._looks_like_deal_email(raw.subject, raw.body):
            return None

        company_name = self._extract_company_name(
            raw.subject, raw.body, raw.from_addr
        )
        if company_name == "Unknown":
            # Gatekeeper would drop these anyway; skip early to keep
            # state files cleaner.
            return None

        domain = self._extract_domain(raw.body, raw.from_addr)
        if not domain:
            return None

        sender = self._extract_sender_address(raw.from_addr)
        return {
            "company_name": company_name,
            "domain": domain,
            "vc_source": "Email",
            "source_url": f"mailto:{sender}" if sender else None,
            "source_email": sender,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "attachment_filenames": raw.attachments,
        }

    # ─── Mailbox polling ─────────────────────────────────────────────

    def _build_raw_email(self, parsed_email) -> _RawEmail:
        body = self._extract_text_body(parsed_email)
        return _RawEmail(
            subject=self._decode_str(parsed_email.get("Subject", "")),
            from_addr=self._decode_str(parsed_email.get("From", "")),
            body=body,
            attachments=self._list_attachment_names(parsed_email),
            message_id=self._decode_str(parsed_email.get("Message-ID", "")),
            date=self._decode_str(parsed_email.get("Date", "")),
        )

    def _poll_pop3(self) -> list[dict]:
        import poplib

        client = None
        companies: list[dict] = []
        try:
            client = poplib.POP3_SSL(self.pop_host, self.pop_port, timeout=30)
            client.user(self.email)
            client.pass_(self.password)
            message_refs = client.list()[1]
            total = len(message_refs)

            uid_by_num: dict[int, str] = {}
            try:
                for line in client.uidl()[1]:
                    parts = line.decode("utf-8", errors="ignore").split()
                    if len(parts) >= 2 and parts[0].isdigit():
                        uid_by_num[int(parts[0])] = parts[1]
            except Exception:
                pass

            start = max(1, total - self.max_messages + 1)
            seen_changed = False
            for msg_num in range(start, total + 1):
                uid = uid_by_num.get(msg_num)
                seen_key = f"pop3:{uid}" if uid else ""
                if seen_key and seen_key in self._seen_ids:
                    continue
                _, lines, _ = client.retr(msg_num)
                parsed = message_from_bytes(b"\r\n".join(lines), policy=policy.default)
                raw = self._build_raw_email(parsed)
                if not seen_key:
                    fallback = self._stable_message_key(parsed, raw.body)
                    seen_key = f"pop3:{fallback}" if fallback else f"pop3:num:{msg_num}"
                    if seen_key in self._seen_ids:
                        continue
                company = self._parse_to_company(raw)
                if company:
                    companies.append(company)
                self._seen_ids.add(seen_key)
                seen_changed = True

            if seen_changed:
                self._save_seen_ids()
            return companies
        except Exception as e:
            raise RuntimeError(f"POP3 error: {e}") from e
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    pass

    def _poll_imap(self) -> list[dict]:
        import imaplib

        client = None
        companies: list[dict] = []
        try:
            client = imaplib.IMAP4_SSL(
                self.imap_host, self.imap_port, timeout=self.imap_timeout_sec
            )
            client.login(self.email, self.password)
            status, _ = client.select("INBOX", readonly=False)
            if status != "OK":
                return []

            use_uid = True
            try:
                status, data = client.uid("search", None, "ALL")
                if status != "OK" or not data:
                    return []
                ids = data[0].split()
            except Exception:
                use_uid = False
                status, data = client.search(None, "ALL")
                if status != "OK" or not data:
                    return []
                ids = data[0].split()

            recent_ids = ids[-self.max_messages :]
            seen_changed = False
            for msg_id in recent_ids:
                seen_key = (
                    f"imap:{msg_id.decode('utf-8', errors='ignore')}"
                    if use_uid
                    else ""
                )
                if seen_key and seen_key in self._seen_ids:
                    continue
                if use_uid:
                    status, payload = client.uid("fetch", msg_id, "(RFC822)")
                else:
                    status, payload = client.fetch(msg_id, "(RFC822)")
                if status != "OK" or not payload:
                    continue
                raw_bytes = b""
                for part in payload:
                    if isinstance(part, tuple):
                        raw_bytes = part[1]
                        break
                if not raw_bytes:
                    continue
                parsed = message_from_bytes(raw_bytes, policy=policy.default)
                raw = self._build_raw_email(parsed)
                if not seen_key:
                    fallback = self._stable_message_key(parsed, raw.body)
                    seq = msg_id.decode("utf-8", errors="ignore")
                    seen_key = (
                        f"imap:{fallback}" if fallback else f"imap:seq:{seq}"
                    )
                    if seen_key in self._seen_ids:
                        continue
                company = self._parse_to_company(raw)
                if company:
                    companies.append(company)
                self._seen_ids.add(seen_key)
                seen_changed = True

            if seen_changed:
                self._save_seen_ids()
            return companies
        except Exception as e:
            raise RuntimeError(f"IMAP error: {e}") from e
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass

    def capture_new_emails(self) -> list[dict]:
        """Poll the inbox once, return new deal-shaped company dicts.

        Returns [] (not None) on missing config or transport failure,
        so harvest can always fold the result into its dedup pass.
        Protocol 'auto' tries POP3 first (matches dealflow behavior)
        and falls back to IMAP if POP3 is administratively disabled
        (the common Gmail Workspace case).
        """
        if not self.configured:
            return []

        if self.protocol == "imap":
            try:
                return self._poll_imap()
            except Exception as e:
                print(f"[EmailCapture] {e}", flush=True)
                return []

        if self.protocol == "pop3":
            try:
                return self._poll_pop3()
            except Exception as e:
                print(f"[EmailCapture] {e}", flush=True)
                return []

        # 'auto' — POP3 first, IMAP fallback on POP3-disabled errors
        try:
            return self._poll_pop3()
        except Exception as pop_error:
            msg = str(pop_error)
            if "not enabled for POP access" in msg or "SYS/PERM" in msg:
                print(
                    "[EmailCapture] POP3 unavailable, falling back to IMAP.",
                    flush=True,
                )
                try:
                    return self._poll_imap()
                except Exception as imap_error:
                    print(f"[EmailCapture] {pop_error}", flush=True)
                    print(f"[EmailCapture] {imap_error}", flush=True)
                    return []
            print(f"[EmailCapture] {pop_error}", flush=True)
            return []
