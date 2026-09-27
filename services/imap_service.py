"""Simple email fetching via IMAP + App Password. No OAuth JSON required.

Works with Gmail, Outlook/Hotmail, Yahoo, and any provider that supports IMAP.
For Gmail, the user needs a Google App Password (16 chars) — created at
https://myaccount.google.com/apppasswords — 2-Step Verification must be on.
"""
import base64
import email as email_lib
import imaplib
import json
import re
import smtplib
import ssl
from datetime import datetime
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from typing import Any

from services import database as db


class ImapError(Exception):
    pass


# ---- Provider presets --------------------------------------------------

PROVIDERS = {
    "gmail": {
        "name": "Gmail",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "help_url": "https://myaccount.google.com/apppasswords",
        "help_text": "Enable 2-Step Verification, then create an App Password.",
    },
    "outlook": {
        "name": "Outlook / Hotmail",
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "help_url": "https://account.microsoft.com/security",
        "help_text": "Turn on 2-step verification, then create an app password.",
    },
    "yahoo": {
        "name": "Yahoo Mail",
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 587,
        "help_url": "https://login.yahoo.com/account/security",
        "help_text": "Enable 2-Step Verification, then generate an app password.",
    },
    "icloud": {
        "name": "iCloud Mail",
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "help_url": "https://appleid.apple.com/account/manage",
        "help_text": "Create an app-specific password from Apple ID account.",
    },
    "custom": {
        "name": "Custom IMAP",
        "imap_host": "",
        "imap_port": 993,
        "smtp_host": "",
        "smtp_port": 587,
        "help_url": "",
        "help_text": "Enter your provider's IMAP/SMTP settings.",
    },
}


# ---- Credential storage (local DB) -------------------------------------

def save_credentials(email: str, password: str, provider: str = "gmail",
                      imap_host: str | None = None, imap_port: int | None = None,
                      smtp_host: str | None = None, smtp_port: int | None = None,
                      display_name: str | None = None) -> None:
    """Store IMAP credentials in the local settings table."""
    preset = PROVIDERS.get(provider, PROVIDERS["gmail"])
    payload = {
        "email": email,
        "password": password,
        "provider": provider,
        "imap_host": imap_host or preset["imap_host"],
        "imap_port": imap_port or preset["imap_port"],
        "smtp_host": smtp_host or preset["smtp_host"],
        "smtp_port": smtp_port or preset["smtp_port"],
        "display_name": display_name or "",
    }
    db.set_setting("imap_credentials", json.dumps(payload))


def get_credentials() -> dict | None:
    raw = db.get_setting("imap_credentials")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def clear_credentials() -> None:
    db.set_setting("imap_credentials", "")


def is_connected() -> bool:
    return bool(get_credentials())


# ---- Connection --------------------------------------------------------

def _connect_imap(creds: dict) -> imaplib.IMAP4_SSL:
    context = ssl.create_default_context()
    try:
        conn = imaplib.IMAP4_SSL(creds["imap_host"], int(creds.get("imap_port", 993)),
                                  ssl_context=context, timeout=25)
    except (OSError, imaplib.IMAP4.error) as e:
        raise ImapError(f"Could not reach {creds['imap_host']}: {e}")
    try:
        conn.login(creds["email"], creds["password"])
    except imaplib.IMAP4.error as e:
        raise ImapError(f"Login failed - check your email and app password. ({e})")
    return conn


def test_connection(email: str, password: str, provider: str = "gmail",
                     imap_host: str | None = None, imap_port: int | None = None) -> None:
    """Attempt a login. Raises ImapError on failure."""
    preset = PROVIDERS.get(provider, PROVIDERS["gmail"])
    creds = {
        "email": email,
        "password": password,
        "imap_host": imap_host or preset["imap_host"],
        "imap_port": imap_port or preset["imap_port"],
    }
    conn = _connect_imap(creds)
    try:
        conn.logout()
    except Exception:
        pass


# ---- Fetching ----------------------------------------------------------

def fetch_messages(max_results: int = 50, mailbox: str = "INBOX",
                    query: str = "") -> list[dict]:
    """Fetch recent messages from the configured mailbox via IMAP."""
    creds = get_credentials()
    if not creds:
        raise ImapError("No IMAP credentials configured.")
    conn = _connect_imap(creds)
    try:
        status, _ = conn.select(mailbox, readonly=True)
        if status != "OK":
            raise ImapError(f"Cannot open mailbox {mailbox}")

        # Build search criteria
        search_criteria = "ALL"
        if query:
            # Very simple query: search subject + body
            safe = re.sub(r'["\\]', "", query)[:100]
            search_criteria = f'(OR SUBJECT "{safe}" BODY "{safe}")'

        status, data = conn.search(None, search_criteria)
        if status != "OK":
            return []

        ids = data[0].split()
        # Newest first, take last N
        ids = ids[-max_results:][::-1]

        results: list[dict] = []
        for msg_id in ids:
            try:
                status, msg_data = conn.fetch(msg_id, "(RFC822 FLAGS)")
                if status != "OK" or not msg_data:
                    continue
                raw = None
                flags_str = ""
                for item in msg_data:
                    if isinstance(item, tuple) and len(item) >= 2:
                        raw = item[1]
                    elif isinstance(item, bytes):
                        flags_str += item.decode(errors="replace")
                if not raw:
                    continue
                msg = email_lib.message_from_bytes(raw)
                parsed = _parse_email(msg, msg_id.decode(), creds["email"], flags_str)
                results.append(parsed)
            except Exception:
                continue
        return results
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def _decode_header_str(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _parse_email(msg, msg_id: str, account_email: str, flags_str: str = "") -> dict:
    subject = _decode_header_str(msg.get("Subject", ""))
    from_raw = _decode_header_str(msg.get("From", ""))
    sender_name, sender_email = parseaddr(from_raw)
    to = _decode_header_str(msg.get("To", ""))
    cc = _decode_header_str(msg.get("Cc", ""))
    date_str = msg.get("Date", "")
    try:
        dt = parsedate_to_datetime(date_str)
        date_iso = dt.isoformat()
    except (TypeError, ValueError):
        date_iso = datetime.utcnow().isoformat()

    body_text, body_html, attachments = _extract_body_and_attachments(msg)
    if not body_text and body_html:
        body_text = _html_to_text(body_html)

    is_read = "\\Seen" in flags_str
    is_starred = "\\Flagged" in flags_str

    # Generate a stable-ish gmail_id substitute from Message-ID header or IMAP id
    message_id_hdr = msg.get("Message-ID") or msg.get("Message-Id") or f"imap_{msg_id}"
    stable_id = "imap_" + re.sub(r"[^a-zA-Z0-9_\-@]", "_", message_id_hdr)[:120]

    # Thread grouping: prefer References/In-Reply-To chain root, else subject-normalized key
    thread_id = _derive_thread_id(msg, subject)

    return {
        "gmail_id": stable_id,
        "thread_id": thread_id,
        "account_email": account_email,
        "subject": subject or "(no subject)",
        "sender": sender_name or sender_email,
        "sender_email": sender_email,
        "recipient": to,
        "cc": cc,
        "date": date_iso,
        "snippet": (body_text or "")[:200].replace("\n", " ").strip(),
        "body_text": body_text[:50000],
        "body_html": body_html[:100000],
        "labels": ["INBOX"] + ([] if is_read else ["UNREAD"]) + (["STARRED"] if is_starred else []),
        "is_read": is_read,
        "is_starred": is_starred,
        "attachments": attachments,
    }


def _extract_body_and_attachments(msg) -> tuple[str, str, list[dict]]:
    text = ""
    html = ""
    attachments: list[dict] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition.lower():
                fname = _decode_header_str(part.get_filename() or "")
                if fname:
                    payload = part.get_payload(decode=True)
                    attachments.append({
                        "filename": fname,
                        "mime_type": ctype,
                        "size": len(payload) if payload else 0,
                    })
                continue
            if ctype == "text/plain" and not text:
                text = _decode_part(part)
            elif ctype == "text/html" and not html:
                html = _decode_part(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            text = _decode_part(msg)
        elif ctype == "text/html":
            html = _decode_part(msg)
    return text, html, attachments


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for s in soup(["script", "style"]):
            s.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n").strip())
    except Exception:
        text = re.sub(r"<[^>]+>", "", html)
        return unescape(text)


def _derive_thread_id(msg, subject: str) -> str:
    """IMAP has no true thread IDs; derive one from References/In-Reply-To or normalized subject."""
    references = msg.get("References") or ""
    in_reply_to = msg.get("In-Reply-To") or ""
    chain = references.split() + in_reply_to.split()
    if chain:
        return "imap_thread_" + re.sub(r"[^a-zA-Z0-9]", "_", chain[0])[:100]
    normalized = re.sub(r"^(re|fwd|fw)\s*:\s*", "", (subject or "").strip(), flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return "imap_subj_" + re.sub(r"[^a-z0-9]", "_", normalized)[:120]


# ---- Sending -----------------------------------------------------------

def send_message(to: str, subject: str, body: str) -> None:
    creds = get_credentials()
    if not creds:
        raise ImapError("No credentials configured.")
    msg = EmailMessage()
    display_name = creds.get("display_name", "")
    msg["From"] = f"{display_name} <{creds['email']}>" if display_name else creds["email"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(creds["smtp_host"], int(creds.get("smtp_port", 587)), timeout=25) as server:
        server.starttls(context=context)
        server.login(creds["email"], creds["password"])
        server.send_message(msg)
