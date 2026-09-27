"""Gmail integration - OAuth flow, message fetching, parsing."""
import base64
import json
import re
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from typing import Any

import config

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


class GmailError(Exception):
    pass


def credentials_configured() -> bool:
    return config.CLIENT_SECRETS_FILE.exists()


def is_authenticated() -> bool:
    if not config.TOKEN_FILE.exists():
        return False
    try:
        creds = _load_credentials()
        return creds is not None and (creds.valid or bool(creds.refresh_token))
    except Exception:
        return False


def get_auth_flow() -> "Flow":
    if not GOOGLE_AVAILABLE:
        raise GmailError("Google API libraries not installed.")
    if not credentials_configured():
        raise GmailError(
            "OAuth client_secret.json not found. Upload it via Settings first."
        )
    flow = Flow.from_client_secrets_file(
        str(config.CLIENT_SECRETS_FILE),
        scopes=config.GMAIL_SCOPES,
        redirect_uri=config.OAUTH_REDIRECT_URI,
    )
    return flow


def save_credentials(creds: "Credentials") -> None:
    config.TOKEN_FILE.write_text(creds.to_json())


def _load_credentials() -> "Credentials | None":
    if not config.TOKEN_FILE.exists() or not GOOGLE_AVAILABLE:
        return None
    data = json.loads(config.TOKEN_FILE.read_text())
    creds = Credentials.from_authorized_user_info(data, config.GMAIL_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
    return creds


def get_service():
    creds = _load_credentials()
    if not creds:
        raise GmailError("Not authenticated with Google.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_user_profile() -> dict:
    service = get_service()
    profile = service.users().getProfile(userId="me").execute()
    return profile


def sign_out() -> None:
    if config.TOKEN_FILE.exists():
        config.TOKEN_FILE.unlink()


# ---- Message fetching --------------------------------------------------

def fetch_messages(max_results: int = 50, query: str = "") -> list[dict]:
    """Fetch recent messages metadata + full payload, parsed to dicts."""
    service = get_service()
    try:
        resp = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query or None)
            .execute()
        )
    except HttpError as e:
        raise GmailError(f"Gmail API error: {e}")

    messages = resp.get("messages", [])
    parsed: list[dict] = []
    for m in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=m["id"], format="full")
                .execute()
            )
            parsed.append(parse_message(msg))
        except HttpError:
            continue
    return parsed


def parse_message(msg: dict) -> dict:
    """Convert Gmail message payload to our email dict format."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender_full = headers.get("from", "")
    sender_name, sender_email = parseaddr(sender_full)
    date_str = headers.get("date", "")
    try:
        dt = parsedate_to_datetime(date_str)
        date_iso = dt.isoformat()
    except (TypeError, ValueError):
        date_iso = datetime.utcnow().isoformat()

    body_text, body_html = _extract_body(msg.get("payload", {}))
    attachments = _extract_attachments(msg.get("payload", {}))

    labels = msg.get("labelIds", [])
    is_read = "UNREAD" not in labels
    is_starred = "STARRED" in labels

    return {
        "gmail_id": msg["id"],
        "thread_id": msg.get("threadId"),
        "subject": headers.get("subject", "(no subject)"),
        "sender": sender_name or sender_email,
        "sender_email": sender_email,
        "recipient": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "date": date_iso,
        "snippet": msg.get("snippet", ""),
        "body_text": body_text[:50000],
        "body_html": body_html[:100000],
        "labels": labels,
        "is_read": is_read,
        "is_starred": is_starred,
        "attachments": attachments,
    }


def _extract_body(payload: dict) -> tuple[str, str]:
    text = ""
    html = ""

    def walk(part: dict):
        nonlocal text, html
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
            except Exception:
                decoded = ""
            if mime == "text/plain" and not text:
                text = decoded
            elif mime == "text/html" and not html:
                html = decoded
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if not text and html:
        text = _html_to_text(html)
    return text, html


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


def _extract_attachments(payload: dict) -> list[dict]:
    out: list[dict] = []

    def walk(part: dict):
        filename = part.get("filename")
        if filename:
            out.append(
                {
                    "filename": filename,
                    "mime_type": part.get("mimeType", ""),
                    "size": part.get("body", {}).get("size", 0),
                }
            )
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return out


def send_message(to: str, subject: str, body: str) -> dict:
    """Send an email via Gmail API."""
    from email.mime.text import MIMEText

    service = get_service()
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()
