"""OpenRouter LLM integration - summarize, extract, categorize, chat, draft."""
import json
import re
from typing import Any

import requests

import config
from services import database as db


class LLMError(Exception):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "HTTP-Referer": config.SITE_URL,
        "X-Title": config.SITE_NAME,
        "Content-Type": "application/json",
    }


def get_active_model() -> str:
    return db.get_setting("llm_model", config.DEFAULT_MODEL) or config.DEFAULT_MODEL


def set_active_model(model: str) -> None:
    db.set_setting("llm_model", model)


def chat_completion(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.4,
    json_mode: bool = False,
) -> str:
    """Call OpenRouter chat completions and return the assistant string."""
    model_to_use = model or get_active_model()
    payload: dict[str, Any] = {
        "model": model_to_use,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(
            config.OPENROUTER_URL, headers=_headers(), json=payload, timeout=90
        )
    except requests.RequestException as e:
        raise LLMError(f"Network error contacting OpenRouter: {e}")

    if resp.status_code == 402:
        raise LLMError("OpenRouter payment required or insufficient credits.")
    if resp.status_code == 401:
        raise LLMError("OpenRouter API key invalid or unauthorized.")
    if not resp.ok:
        # Try fallback model once
        if model_to_use != config.FALLBACK_MODEL:
            payload["model"] = config.FALLBACK_MODEL
            payload.pop("response_format", None)
            try:
                fb = requests.post(
                    config.OPENROUTER_URL, headers=_headers(), json=payload, timeout=90
                )
                if fb.ok:
                    return fb.json()["choices"][0]["message"]["content"]
            except requests.RequestException:
                pass
        raise LLMError(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")

    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"Unexpected OpenRouter response shape: {e}")


def _extract_json(raw: str) -> dict:
    """Best-effort JSON extraction from an LLM response."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        obj = re.search(r"\{.*\}", raw, re.DOTALL)
        if obj:
            raw = obj.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"summary": raw, "key_points": [], "action_items": [], "sentiment": "unknown", "entities": []}


# ---- Public analysis APIs ---------------------------------------------

def summarize_email(email: dict) -> dict:
    """Produce a structured single-email analysis."""
    body = (email.get("body_text") or email.get("snippet") or "").strip()[:6000]
    prompt = f"""Analyze this email and return STRICT JSON matching this schema:
{{
  "summary": "2-3 sentence summary of the email",
  "key_points": ["bullet", "point", "list"],
  "action_items": ["actionable items or requests directed at the recipient"],
  "sentiment": "positive|neutral|negative|urgent",
  "priority_score": 1-10 integer,
  "category": "work|personal|finance|travel|shopping|promotional|newsletter|security|social|other",
  "entities": ["people, orgs, dates, amounts mentioned"],
  "suggested_response": "optional 1-2 sentence suggestion of what a reply might say, or empty string"
}}

Subject: {email.get('subject', '')}
From: {email.get('sender', '')} <{email.get('sender_email', '')}>
Date: {email.get('date', '')}

Body:
{body}

Return ONLY the JSON object, no prose."""

    result_text = chat_completion(
        [
            {"role": "system", "content": "You are an expert email analyst. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        json_mode=True,
        max_tokens=900,
        temperature=0.3,
    )
    data = _extract_json(result_text)
    return {
        "summary": data.get("summary", ""),
        "key_points": data.get("key_points", []) or [],
        "action_items": data.get("action_items", []) or [],
        "sentiment": data.get("sentiment", "neutral"),
        "priority_score": int(data.get("priority_score", 5) or 5),
        "category": data.get("category", "other"),
        "entities": data.get("entities", []) or [],
        "metadata": {"suggested_response": data.get("suggested_response", "")},
    }


def summarize_thread(emails: list[dict]) -> dict:
    """Summarize a whole thread as a conversation."""
    if not emails:
        return {"summary": "", "key_points": [], "action_items": [], "sentiment": "neutral", "entities": []}
    convo_parts = []
    for e in emails[:15]:  # cap
        body = (e.get("body_text") or e.get("snippet") or "")[:2500]
        convo_parts.append(
            f"--- From: {e.get('sender', '')} <{e.get('sender_email', '')}>\n"
            f"Date: {e.get('date', '')}\n"
            f"Subject: {e.get('subject', '')}\n\n{body}\n"
        )
    convo = "\n".join(convo_parts)
    prompt = f"""You are analyzing an email conversation thread with {len(emails)} messages. Return STRICT JSON:
{{
  "summary": "4-6 sentence executive summary of the whole conversation",
  "key_points": ["most important 4-8 points"],
  "action_items": ["outstanding actions and who owns them"],
  "sentiment": "positive|neutral|negative|urgent|mixed",
  "decisions_made": ["decisions reached in the thread"],
  "open_questions": ["questions still unanswered"],
  "entities": ["important people, orgs, dates, amounts"],
  "timeline": "one-line description of how the conversation evolved"
}}

Conversation:
{convo}

Return ONLY the JSON object."""
    result_text = chat_completion(
        [
            {"role": "system", "content": "You are an expert email thread analyst. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        json_mode=True,
        max_tokens=1400,
        temperature=0.3,
    )
    data = _extract_json(result_text)
    return {
        "summary": data.get("summary", ""),
        "key_points": data.get("key_points", []) or [],
        "action_items": data.get("action_items", []) or [],
        "sentiment": data.get("sentiment", "neutral"),
        "entities": data.get("entities", []) or [],
        "metadata": {
            "decisions_made": data.get("decisions_made", []),
            "open_questions": data.get("open_questions", []),
            "timeline": data.get("timeline", ""),
            "message_count": len(emails),
        },
    }


def categorize_email(email: dict) -> tuple[str, int, str]:
    """Fast classification: category, priority (1-10), sentiment."""
    body = (email.get("body_text") or email.get("snippet") or "")[:2000]
    prompt = f"""Classify this email and return STRICT JSON:
{{
  "category": "work|personal|finance|travel|shopping|promotional|newsletter|security|social|other",
  "priority": 1-10 integer,
  "sentiment": "positive|neutral|negative|urgent"
}}

Subject: {email.get('subject', '')}
From: {email.get('sender', '')}
Body: {body}"""
    result_text = chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=True, max_tokens=150, temperature=0.1,
    )
    data = _extract_json(result_text)
    return (
        data.get("category", "other"),
        int(data.get("priority", 5) or 5),
        data.get("sentiment", "neutral"),
    )


def draft_reply(email: dict, tone: str = "professional", intent: str = "acknowledge and respond") -> str:
    body = (email.get("body_text") or email.get("snippet") or "")[:4000]
    prompt = f"""Draft an email reply.

Tone: {tone}
Intent: {intent}

Original email:
Subject: {email.get('subject', '')}
From: {email.get('sender', '')} <{email.get('sender_email', '')}>

{body}

Draft only the reply body, no subject line or headers. Use appropriate greeting and sign-off. Keep it concise unless the content warrants length."""
    return chat_completion(
        [
            {"role": "system", "content": "You are an expert email writing assistant."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=700, temperature=0.7,
    )


def answer_question_about_emails(question: str, emails: list[dict], history: list[dict] | None = None) -> str:
    """Chat about emails - the assistant sees a selection of emails as context."""
    context_parts = []
    for e in emails[:15]:
        body = (e.get("body_text") or e.get("snippet") or "")[:1200]
        context_parts.append(
            f"[Email #{e['id']}] From: {e.get('sender', '')} | "
            f"Subject: {e.get('subject', '')} | Date: {e.get('date', '')}\n"
            f"{body}\n---"
        )
    context = "\n".join(context_parts) if context_parts else "(no matching emails found)"

    messages = [
        {
            "role": "system",
            "content": (
                "You are the user's personal email assistant. You have access to a selection "
                "of their emails as context. Answer their questions directly using only the "
                "email context. Reference emails by their #ID when relevant. If the context "
                "does not contain the answer, say so."
            ),
        }
    ]
    for h in (history or [])[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({
        "role": "user",
        "content": f"Email context:\n{context}\n\nUser question: {question}",
    })
    return chat_completion(messages, max_tokens=900, temperature=0.5)


def generate_executive_digest(emails: list[dict]) -> dict:
    """Generate a digest across many emails - for weekly reports."""
    if not emails:
        return {"summary": "No emails.", "themes": [], "priorities": [], "insights": []}
    items = []
    for e in emails[:40]:
        items.append(
            f"- {e.get('date', '')[:10]} | {e.get('sender', '')} | "
            f"{e.get('subject', '')} | {(e.get('snippet') or '')[:150]}"
        )
    listing = "\n".join(items)
    prompt = f"""Produce a STRICT-JSON executive digest of these {len(emails)} recent emails:
{{
  "summary": "4-6 sentence overview of what's been happening",
  "themes": ["3-6 dominant themes"],
  "priorities": ["top 3-5 things that need attention"],
  "insights": ["3-5 non-obvious insights, patterns, or recommendations"],
  "top_correspondents": ["most important people to respond to"],
  "recommended_actions": ["3-5 concrete next steps for the user"]
}}

Emails:
{listing}

Return ONLY the JSON object."""
    result_text = chat_completion(
        [
            {"role": "system", "content": "You are a strategic email analyst. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        json_mode=True, max_tokens=1400, temperature=0.4,
    )
    data = _extract_json(result_text)
    return {
        "summary": data.get("summary", ""),
        "themes": data.get("themes", []) or [],
        "priorities": data.get("priorities", []) or [],
        "insights": data.get("insights", []) or [],
        "top_correspondents": data.get("top_correspondents", []) or [],
        "recommended_actions": data.get("recommended_actions", []) or [],
    }


def detect_chat_intent(message: str, contacts: list[dict], sender_name: str = "") -> dict:
    """Detect if the user wants to send an email or delete an email from chat."""
    contacts_list = ", ".join(f"{c['name']} ({c['email']})" for c in contacts) if contacts else "(none)"
    sender_info = f"\nThe sender's name is: {sender_name}. Use this name for the sign-off instead of '[Your Name]' or any placeholder." if sender_name else ""
    prompt = f"""Analyze this user message and determine the intent. Return STRICT JSON:
{{
  "intent": "send_email" | "delete_email" | "question",
  "to_email": "recipient email address if intent is send_email, else empty string",
  "to_name": "recipient name if resolved from contacts, else empty string",
  "subject": "email subject if intent is send_email, else empty string",
  "body": "email body text if intent is send_email, else empty string",
  "email_id": integer email ID if intent is delete_email (extract from message like 'delete email #5'), else null,
  "confidence": 0.0 to 1.0
}}

Available contacts: {contacts_list}

Rules:
- If the user says something like "send an email to mom saying..." or "draft a mail to xyz@gmail.com", intent is "send_email"
- If a contact name is used (e.g. "mom"), resolve it to the email from the contacts list
- If the user says "delete email #5" or "remove email 3", intent is "delete_email"
- Otherwise, intent is "question"
- For send_email, compose a professional email body based on what the user wants to communicate
- NEVER use "[Your Name]" or any placeholder in the sign-off. Use the sender's actual name.{sender_info}

User message: {message}"""
    try:
        result_text = chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True, max_tokens=500, temperature=0.2,
        )
        return _extract_json(result_text)
    except LLMError:
        return {"intent": "question", "confidence": 0}


def semantic_related_search(query: str, emails: list[dict], top_k: int = 8) -> list[int]:
    """Use LLM to rank a candidate set of emails by relevance to query. Returns email IDs."""
    if not emails:
        return []
    candidates = []
    for e in emails[:60]:
        snippet = (e.get("snippet") or e.get("body_text") or "")[:300]
        candidates.append(f"ID:{e['id']} | {e.get('subject', '')} | {e.get('sender', '')} | {snippet}")
    listing = "\n".join(candidates)
    prompt = f"""Rank these emails by relevance to the query. Return STRICT JSON:
{{"ranked_ids": [list of email IDs in relevance order]}}

Query: {query}

Emails:
{listing}

Return ONLY the JSON. Include up to {top_k} of the most relevant IDs."""
    try:
        result_text = chat_completion(
            [{"role": "user", "content": prompt}],
            json_mode=True, max_tokens=200, temperature=0.1,
        )
        data = _extract_json(result_text)
        ids = data.get("ranked_ids", []) or []
        return [int(x) for x in ids if str(x).isdigit()][:top_k]
    except (LLMError, ValueError):
        return [e["id"] for e in emails[:top_k]]
