"""SQLite database layer for storing emails, threads, analyses, and reports."""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    connected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_sync TEXT
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_id TEXT UNIQUE NOT NULL,
    thread_id TEXT,
    account_email TEXT,
    subject TEXT,
    sender TEXT,
    sender_email TEXT,
    recipient TEXT,
    cc TEXT,
    date TEXT,
    snippet TEXT,
    body_text TEXT,
    body_html TEXT,
    labels TEXT,
    is_read INTEGER DEFAULT 0,
    is_starred INTEGER DEFAULT 0,
    attachments TEXT,
    category TEXT,
    priority INTEGER DEFAULT 0,
    sentiment TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date);
CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER,
    thread_id TEXT,
    analysis_type TEXT,
    summary TEXT,
    key_points TEXT,
    action_items TEXT,
    sentiment TEXT,
    entities TEXT,
    metadata TEXT,
    model_used TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (email_id) REFERENCES emails(id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_email ON analyses(email_id);
CREATE INDEX IF NOT EXISTS idx_analyses_thread ON analyses(thread_id);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    report_type TEXT,
    file_path TEXT,
    filters TEXT,
    email_count INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role TEXT,
    content TEXT,
    referenced_emails TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
"""


def init_db() -> None:
    conn = sqlite3.connect(str(config.DATABASE_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(config.DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---- Emails ------------------------------------------------------------

def upsert_email(email: dict[str, Any]) -> int:
    """Insert or update an email by gmail_id. Returns local row id."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM emails WHERE gmail_id = ?", (email["gmail_id"],)
        ).fetchone()
        payload = {
            "gmail_id": email["gmail_id"],
            "thread_id": email.get("thread_id"),
            "account_email": email.get("account_email"),
            "subject": email.get("subject", ""),
            "sender": email.get("sender", ""),
            "sender_email": email.get("sender_email", ""),
            "recipient": email.get("recipient", ""),
            "cc": email.get("cc", ""),
            "date": email.get("date", ""),
            "snippet": email.get("snippet", ""),
            "body_text": email.get("body_text", ""),
            "body_html": email.get("body_html", ""),
            "labels": json.dumps(email.get("labels", [])),
            "is_read": int(email.get("is_read", False)),
            "is_starred": int(email.get("is_starred", False)),
            "attachments": json.dumps(email.get("attachments", [])),
            "category": email.get("category"),
            "priority": email.get("priority", 0),
            "sentiment": email.get("sentiment"),
        }
        if existing:
            fields = ", ".join(f"{k} = :{k}" for k in payload)
            conn.execute(f"UPDATE emails SET {fields} WHERE gmail_id = :gmail_id", payload)
            return existing["id"]
        cols = ", ".join(payload.keys())
        placeholders = ", ".join(f":{k}" for k in payload.keys())
        cur = conn.execute(f"INSERT INTO emails ({cols}) VALUES ({placeholders})", payload)
        return cur.lastrowid


def get_email(email_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        return _decode_email(row) if row else None


def get_email_by_gmail_id(gmail_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM emails WHERE gmail_id = ?", (gmail_id,)).fetchone()
        return _decode_email(row) if row else None


def _parse_search_operators(search: str) -> tuple[str, dict]:
    """Extract Gmail-style operators from search string.

    Supports: from:xyz, to:xyz, subject:xyz, has:attachment,
    is:unread, is:read, is:starred, category:xyz, priority:high|med|low
    Returns (remaining_text, operator_dict).
    """
    import re as _re
    ops: dict = {}
    remaining = search

    # from:  to:  subject:  category:  priority:
    for op in ("from", "to", "subject", "category", "priority"):
        m = _re.search(rf'{op}:"([^"]+)"|{op}:(\S+)', remaining, _re.IGNORECASE)
        if m:
            ops[op] = m.group(1) or m.group(2)
            remaining = remaining[:m.start()] + remaining[m.end():]

    # has:attachment / has:analysis
    m = _re.search(r'has:(attachment|analysis)', remaining, _re.IGNORECASE)
    if m:
        ops["has"] = m.group(1).lower()
        remaining = remaining[:m.start()] + remaining[m.end():]

    # is:unread / is:read / is:starred
    m = _re.search(r'is:(unread|read|starred)', remaining, _re.IGNORECASE)
    if m:
        ops["is"] = m.group(1).lower()
        remaining = remaining[:m.start()] + remaining[m.end():]

    return remaining.strip(), ops


def list_emails(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    category: str | None = None,
    priority_min: int | None = None,
    sender: str | None = None,
    sort_by: str = "date",
    sort_dir: str = "DESC",
) -> list[dict]:
    query = "SELECT * FROM emails WHERE 1=1"
    params: list[Any] = []

    text_search = search
    ops: dict = {}
    if search:
        text_search, ops = _parse_search_operators(search)

    if text_search:
        like = f"%{text_search}%"
        query += " AND (subject LIKE ? OR body_text LIKE ? OR sender LIKE ? OR snippet LIKE ?)"
        params.extend([like, like, like, like])

    if ops.get("from"):
        like = f"%{ops['from']}%"
        query += " AND (sender LIKE ? OR sender_email LIKE ?)"
        params.extend([like, like])
    if ops.get("to"):
        query += " AND recipient LIKE ?"
        params.append(f"%{ops['to']}%")
    if ops.get("subject"):
        query += " AND subject LIKE ?"
        params.append(f"%{ops['subject']}%")
    if ops.get("category"):
        query += " AND category = ?"
        params.append(ops["category"].lower())
    priority_map = {"high": 8, "med": 5, "medium": 5, "low": 1}
    if ops.get("priority") and ops["priority"].lower() in priority_map:
        query += " AND priority >= ?"
        params.append(priority_map[ops["priority"].lower()])
    if ops.get("has") == "attachment":
        query += " AND attachments != '[]' AND attachments IS NOT NULL"
    if ops.get("has") == "analysis":
        query += " AND id IN (SELECT DISTINCT email_id FROM analyses WHERE email_id IS NOT NULL)"
    if ops.get("is") == "unread":
        query += " AND is_read = 0"
    if ops.get("is") == "read":
        query += " AND is_read = 1"
    if ops.get("is") == "starred":
        query += " AND is_starred = 1"

    if category:
        query += " AND category = ?"
        params.append(category)
    if priority_min is not None:
        query += " AND priority >= ?"
        params.append(priority_min)
    if sender:
        query += " AND sender_email LIKE ?"
        params.append(f"%{sender}%")

    sort_by = sort_by if sort_by in {"date", "priority", "sender", "subject"} else "date"
    sort_dir = "ASC" if sort_dir.upper() == "ASC" else "DESC"
    query += f" ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_decode_email(r) for r in rows]


def count_emails(search: str | None = None, category: str | None = None) -> int:
    # Reuse list_emails logic by fetching a large limit and counting;
    # for large datasets, we'd inline the filter — but for the local single-user
    # scale this is simpler and stays consistent with list_emails.
    return len(list_emails(limit=100000, search=search, category=category))


def list_thread(thread_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM emails WHERE thread_id = ? ORDER BY date ASC", (thread_id,)
        ).fetchall()
        return [_decode_email(r) for r in rows]


def find_related_emails(email: dict, limit: int = 15) -> list[dict]:
    """Find emails related to a given email — first by thread, then by
    normalized-subject match, then by sender email. Excludes the source email."""
    import re as _re

    with get_conn() as conn:
        results: list[dict] = []
        seen = {email.get("id")}

        # 1. Same thread
        if email.get("thread_id"):
            rows = conn.execute(
                "SELECT * FROM emails WHERE thread_id = ? AND id != ? ORDER BY date ASC",
                (email["thread_id"], email["id"]),
            ).fetchall()
            for r in rows:
                d = _decode_email(r)
                if d["id"] not in seen:
                    results.append(d)
                    seen.add(d["id"])

        # 2. Same normalized subject
        subject = email.get("subject", "") or ""
        normalized = _re.sub(r"^(re|fwd|fw)\s*:\s*", "", subject.strip(), flags=_re.IGNORECASE).strip()
        if normalized and len(results) < limit:
            rows = conn.execute(
                """SELECT * FROM emails
                   WHERE (subject = ? OR subject LIKE ? OR subject LIKE ? OR subject LIKE ?)
                     AND id NOT IN ({})
                   ORDER BY date ASC LIMIT ?""".format(",".join(["?"] * len(seen))),
                (normalized, f"Re: {normalized}", f"Fwd: {normalized}", f"RE: {normalized}",
                 *seen, limit - len(results)),
            ).fetchall()
            for r in rows:
                d = _decode_email(r)
                if d["id"] not in seen:
                    results.append(d)
                    seen.add(d["id"])

        # 3. Same sender_email (if we still have room)
        if email.get("sender_email") and len(results) < limit:
            remaining = limit - len(results)
            rows = conn.execute(
                """SELECT * FROM emails WHERE sender_email = ?
                   AND id NOT IN ({}) ORDER BY date DESC LIMIT ?""".format(",".join(["?"] * len(seen))),
                (email["sender_email"], *seen, remaining),
            ).fetchall()
            for r in rows:
                d = _decode_email(r)
                if d["id"] not in seen:
                    results.append(d)
                    seen.add(d["id"])

        return results[:limit]


def list_threads(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT thread_id,
                   MAX(subject) as subject,
                   COUNT(*) as message_count,
                   MAX(date) as last_date,
                   GROUP_CONCAT(DISTINCT sender_email) as participants
            FROM emails
            WHERE thread_id IS NOT NULL
            GROUP BY thread_id
            HAVING message_count > 0
            ORDER BY last_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_email_fields(email_id: int, **fields) -> None:
    if not fields:
        return
    with get_conn() as conn:
        assigns = ", ".join(f"{k} = ?" for k in fields.keys())
        conn.execute(f"UPDATE emails SET {assigns} WHERE id = ?", (*fields.values(), email_id))


def delete_all_emails() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM emails")
        conn.execute("DELETE FROM analyses")


def _decode_email(row) -> dict:
    d = dict(row)
    for k in ("labels", "attachments"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    return d


# ---- Analyses ----------------------------------------------------------

def save_analysis(
    email_id: int | None,
    thread_id: str | None,
    analysis_type: str,
    result: dict,
    model_used: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO analyses
                (email_id, thread_id, analysis_type, summary, key_points, action_items,
                 sentiment, entities, metadata, model_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email_id,
                thread_id,
                analysis_type,
                result.get("summary", ""),
                json.dumps(result.get("key_points", [])),
                json.dumps(result.get("action_items", [])),
                result.get("sentiment", ""),
                json.dumps(result.get("entities", [])),
                json.dumps(result.get("metadata", {})),
                model_used,
            ),
        )
        return cur.lastrowid


def get_analysis_for_email(email_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE email_id = ? ORDER BY created_at DESC LIMIT 1",
            (email_id,),
        ).fetchone()
        return _decode_analysis(row) if row else None


def get_analysis_for_thread(thread_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM analyses
               WHERE thread_id = ? AND analysis_type = 'thread'
               ORDER BY created_at DESC LIMIT 1""",
            (thread_id,),
        ).fetchone()
        return _decode_analysis(row) if row else None


def _decode_analysis(row) -> dict:
    d = dict(row)
    for k in ("key_points", "action_items", "entities", "metadata"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    return d


# ---- Reports -----------------------------------------------------------

def save_report(title: str, report_type: str, file_path: str, filters: dict, email_count: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reports (title, report_type, file_path, filters, email_count)
               VALUES (?, ?, ?, ?, ?)""",
            (title, report_type, file_path, json.dumps(filters), email_count),
        )
        return cur.lastrowid


def list_reports() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_report(report_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return dict(row) if row else None


def delete_report(report_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))


# ---- Chat --------------------------------------------------------------

def save_chat_message(session_id: str, role: str, content: str, referenced: list | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO chat_history (session_id, role, content, referenced_emails)
               VALUES (?, ?, ?, ?)""",
            (session_id, role, content, json.dumps(referenced or [])),
        )
        return cur.lastrowid


def get_chat_history(session_id: str, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM chat_history WHERE session_id = ?
               ORDER BY created_at ASC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["referenced_emails"] = json.loads(d.get("referenced_emails") or "[]")
            except json.JSONDecodeError:
                d["referenced_emails"] = []
            out.append(d)
        return out


def clear_chat_history(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))


# ---- Accounts ----------------------------------------------------------

def upsert_account(email: str, display_name: str = "") -> None:
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE accounts SET display_name = ?, last_sync = ? WHERE email = ?",
                (display_name, datetime.utcnow().isoformat(), email),
            )
        else:
            conn.execute(
                "INSERT INTO accounts (email, display_name, last_sync) VALUES (?, ?, ?)",
                (email, display_name, datetime.utcnow().isoformat()),
            )


def get_active_account() -> dict | None:
    with get_conn() as conn:
        # Prefer non-demo accounts, then most recent
        row = conn.execute(
            """SELECT * FROM accounts
               WHERE email != 'demo@example.com'
               ORDER BY connected_at DESC LIMIT 1"""
        ).fetchone()
        if row:
            return dict(row)
        row = conn.execute(
            "SELECT * FROM accounts ORDER BY connected_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_active_account_by_email(email: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def delete_account(email: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM accounts WHERE email = ?", (email,))


# ---- Stats -------------------------------------------------------------

def stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"]
        unread = conn.execute("SELECT COUNT(*) c FROM emails WHERE is_read=0").fetchone()["c"]
        starred = conn.execute("SELECT COUNT(*) c FROM emails WHERE is_starred=1").fetchone()["c"]
        threads = conn.execute(
            "SELECT COUNT(DISTINCT thread_id) c FROM emails WHERE thread_id IS NOT NULL"
        ).fetchone()["c"]
        analyzed = conn.execute("SELECT COUNT(DISTINCT email_id) c FROM analyses").fetchone()["c"]
        reports = conn.execute("SELECT COUNT(*) c FROM reports").fetchone()["c"]
        categories = conn.execute(
            "SELECT category, COUNT(*) c FROM emails WHERE category IS NOT NULL GROUP BY category"
        ).fetchall()
        senders = conn.execute(
            """SELECT sender, sender_email, COUNT(*) c FROM emails
               WHERE sender IS NOT NULL AND sender != ''
               GROUP BY sender_email ORDER BY c DESC LIMIT 8"""
        ).fetchall()
        return {
            "total": total,
            "unread": unread,
            "starred": starred,
            "threads": threads,
            "analyzed": analyzed,
            "reports": reports,
            "categories": [dict(c) for c in categories],
            "top_senders": [dict(s) for s in senders],
        }


def timeline() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT substr(date, 1, 10) as day, COUNT(*) c
               FROM emails
               WHERE date IS NOT NULL AND date != ''
               GROUP BY day ORDER BY day DESC LIMIT 30"""
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))


# ---- Settings ----------------------------------------------------------

# ---- Contacts ----------------------------------------------------------

def add_contact(name: str, email: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO contacts (name, email) VALUES (?, ?)", (name.strip(), email.strip())
        )
        return cur.lastrowid


def list_contacts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM contacts ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]


def get_contact_by_name(name: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM contacts WHERE LOWER(name) = LOWER(?)", (name.strip(),)
        ).fetchone()
        return dict(row) if row else None


def delete_contact(contact_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def delete_email_by_id(email_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM analyses WHERE email_id = ?", (email_id,))
        conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
        return True


# ---- Settings ----------------------------------------------------------

def get_setting(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
