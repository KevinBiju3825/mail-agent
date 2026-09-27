"""Mail Agent - AI Email Intelligence Platform."""
import json
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, jsonify, redirect, render_template, request, send_file, session, url_for, flash,
)
from werkzeug.utils import secure_filename

import config
from services import database as db
from services import gmail_service, imap_service, llm_service, pdf_generator
from services.demo_data import seed_demo_emails


app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB (for OAuth JSON upload)


@app.before_request
def _ensure_session_id():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex


@app.context_processor
def _inject_globals():
    imap_creds = imap_service.get_credentials()
    gmail_ok = gmail_service.is_authenticated()

    # Prefer the actually-connected account over any leftover demo account
    current_account = None
    if imap_creds and imap_creds.get("email"):
        current_account = {"email": imap_creds["email"], "display_name": imap_creds["email"],
                           "last_sync": None}
        db_acct = db.get_active_account_by_email(imap_creds["email"])
        if db_acct:
            current_account["last_sync"] = db_acct.get("last_sync")
    elif gmail_ok:
        try:
            profile = gmail_service.get_user_profile()
            current_account = {"email": profile.get("emailAddress", ""),
                                "display_name": profile.get("emailAddress", ""),
                                "last_sync": None}
        except Exception:
            current_account = db.get_active_account()
    else:
        current_account = db.get_active_account()

    return {
        "gmail_connected": gmail_ok,
        "credentials_configured": gmail_service.credentials_configured(),
        "imap_connected": imap_service.is_connected(),
        "imap_credentials": imap_creds,
        "any_connected": gmail_ok or imap_service.is_connected(),
        "current_account": current_account,
        "app_name": config.SITE_NAME,
        "current_year": datetime.utcnow().year,
    }


# ---- Pages -------------------------------------------------------------

@app.route("/")
def index():
    stats = db.stats()
    recent = db.list_emails(limit=8)
    timeline = db.timeline()
    return render_template("index.html", stats=stats, recent=recent, timeline=timeline)


@app.route("/emails")
def emails_page():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip() or None
    sender = request.args.get("sender", "").strip() or None
    priority_min_raw = request.args.get("priority_min")
    try:
        priority_min = int(priority_min_raw) if priority_min_raw else None
    except ValueError:
        priority_min = None
    sort_by = request.args.get("sort", "date")
    page = max(1, int(request.args.get("page", 1) or 1))
    limit = 25
    emails = db.list_emails(
        limit=limit, offset=(page - 1) * limit, search=q,
        category=category, sender=sender, priority_min=priority_min, sort_by=sort_by,
    )
    total = db.count_emails(search=q, category=category)
    return render_template(
        "emails.html", emails=emails, q=q, category=category, sender=sender,
        priority_min=priority_min, sort_by=sort_by, page=page, limit=limit, total=total,
    )


@app.route("/email/<int:email_id>")
def email_detail(email_id: int):
    email = db.get_email(email_id)
    if not email:
        return render_template("404.html"), 404
    thread = db.list_thread(email["thread_id"]) if email.get("thread_id") else [email]
    # If thread only has 1 message, find related by subject / sender as fallback
    related = []
    if len(thread) <= 1:
        related = db.find_related_emails(email, limit=15)
    analysis = db.get_analysis_for_email(email_id)
    thread_analysis = db.get_analysis_for_thread(email["thread_id"]) if email.get("thread_id") else None
    return render_template(
        "email_detail.html", email=email, thread=thread, related=related,
        analysis=analysis, thread_analysis=thread_analysis,
    )


@app.route("/threads")
def threads_page():
    threads = db.list_threads(limit=100)
    return render_template("threads.html", threads=threads)


@app.route("/chat")
def chat_page():
    history = db.get_chat_history(session["sid"])
    return render_template("chat.html", history=history)


@app.route("/reports")
def reports_page():
    reports = db.list_reports()
    return render_template("reports.html", reports=reports)


@app.route("/analytics")
def analytics_page():
    stats = db.stats()
    timeline = db.timeline()
    return render_template("analytics.html", stats=stats, timeline=timeline)


@app.route("/settings")
def settings_page():
    model = llm_service.get_active_model()
    accounts = db.get_active_account()
    return render_template(
        "settings.html", model=model, account=accounts,
        imap_providers=imap_service.PROVIDERS,
    )


# ---- OAuth -------------------------------------------------------------

@app.route("/oauth/upload-credentials", methods=["POST"])
def upload_credentials():
    file = request.files.get("credentials")
    if not file or file.filename == "":
        flash("Please choose a credentials JSON file.", "error")
        return redirect(url_for("settings_page"))
    try:
        data = json.loads(file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash("File is not valid JSON.", "error")
        return redirect(url_for("settings_page"))
    if not any(k in data for k in ("web", "installed")):
        flash("This does not look like a Google OAuth client_secret.json file.", "error")
        return redirect(url_for("settings_page"))
    config.CLIENT_SECRETS_FILE.write_text(json.dumps(data, indent=2))
    flash("OAuth credentials saved. You can now connect your Google account.", "success")
    return redirect(url_for("settings_page"))


@app.route("/oauth/connect")
def oauth_connect():
    try:
        flow = gmail_service.get_auth_flow()
    except gmail_service.GmailError as e:
        flash(str(e), "error")
        return redirect(url_for("settings_page"))
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/oauth/callback")
def oauth_callback():
    if "error" in request.args:
        flash(f"OAuth error: {request.args['error']}", "error")
        return redirect(url_for("settings_page"))
    try:
        flow = gmail_service.get_auth_flow()
        flow.fetch_token(authorization_response=request.url)
        gmail_service.save_credentials(flow.credentials)
        profile = gmail_service.get_user_profile()
        db.upsert_account(profile.get("emailAddress", ""), profile.get("emailAddress", ""))
        flash(f"Connected to {profile.get('emailAddress', 'Gmail')}!", "success")
    except Exception as e:
        flash(f"Could not complete OAuth: {e}", "error")
    return redirect(url_for("index"))


@app.route("/imap/connect", methods=["POST"])
def imap_connect():
    display_name = (request.form.get("display_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()
    provider = (request.form.get("provider") or "gmail").strip()
    imap_host = (request.form.get("imap_host") or "").strip() or None
    imap_port_raw = (request.form.get("imap_port") or "").strip()
    smtp_host = (request.form.get("smtp_host") or "").strip() or None
    smtp_port_raw = (request.form.get("smtp_port") or "").strip()
    imap_port = int(imap_port_raw) if imap_port_raw.isdigit() else None
    smtp_port = int(smtp_port_raw) if smtp_port_raw.isdigit() else None

    if not email or not password:
        flash("Email and app password are both required.", "error")
        return redirect(url_for("settings_page"))
    # Remove spaces the way Google displays app passwords
    password = password.replace(" ", "")
    try:
        imap_service.test_connection(email, password, provider, imap_host, imap_port)
    except imap_service.ImapError as e:
        flash(f"Could not connect: {e}", "error")
        return redirect(url_for("settings_page"))
    imap_service.save_credentials(email, password, provider, imap_host, imap_port, smtp_host, smtp_port, display_name)
    db.upsert_account(email, display_name or email)
    flash(f"Connected {email} via IMAP! You can now sync your emails.", "success")
    return redirect(url_for("settings_page"))


@app.route("/imap/disconnect", methods=["POST"])
def imap_disconnect():
    creds = imap_service.get_credentials()
    imap_service.clear_credentials()
    if creds and creds.get("email"):
        db.delete_account(creds["email"])
    flash("Disconnected IMAP account.", "success")
    return redirect(url_for("settings_page"))


@app.route("/oauth/disconnect", methods=["POST"])
def oauth_disconnect():
    gmail_service.sign_out()
    account = db.get_active_account()
    if account:
        db.delete_account(account["email"])
    flash("Disconnected from Gmail.", "success")
    return redirect(url_for("settings_page"))


# ---- Data / sync -------------------------------------------------------

@app.route("/api/sync", methods=["POST"])
def api_sync():
    body = request.get_json(silent=True) or {}
    limit = min(int(body.get("limit", config.DEFAULT_FETCH_LIMIT)), config.MAX_FETCH_LIMIT)
    query = (body.get("query", "") or "").strip()

    # Prefer OAuth if connected, else IMAP
    if gmail_service.is_authenticated():
        try:
            account = gmail_service.get_user_profile().get("emailAddress", "")
            msgs = gmail_service.fetch_messages(max_results=limit, query=query)
            for m in msgs:
                m["account_email"] = account
                db.upsert_email(m)
            db.upsert_account(account, account)
            return jsonify({"synced": len(msgs), "account": account, "via": "gmail_api"})
        except gmail_service.GmailError as e:
            return jsonify({"error": str(e)}), 500

    if imap_service.is_connected():
        try:
            creds = imap_service.get_credentials()
            msgs = imap_service.fetch_messages(max_results=limit, query=query)
            for m in msgs:
                db.upsert_email(m)
            db.upsert_account(creds["email"], creds["email"])
            return jsonify({"synced": len(msgs), "account": creds["email"], "via": "imap"})
        except imap_service.ImapError as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "No email account connected. Go to Settings to connect."}), 401


@app.route("/api/load-demo", methods=["POST"])
def api_load_demo():
    account = "demo@example.com"
    demo_emails = seed_demo_emails(account)
    for e in demo_emails:
        db.upsert_email(e)
    db.upsert_account(account, "Demo User")
    return jsonify({"loaded": len(demo_emails)})


@app.route("/api/clear-data", methods=["POST"])
def api_clear():
    db.delete_all_emails()
    return jsonify({"ok": True})


# ---- Analysis ----------------------------------------------------------

@app.route("/api/email/<int:email_id>/analyze", methods=["POST"])
def api_analyze_email(email_id: int):
    email = db.get_email(email_id)
    if not email:
        return jsonify({"error": "Email not found"}), 404
    try:
        result = llm_service.summarize_email(email)
    except llm_service.LLMError as e:
        return jsonify({"error": str(e)}), 500
    db.save_analysis(email_id, email.get("thread_id"), "email", result, llm_service.get_active_model())
    # Also update category/priority/sentiment on the email row
    updates = {}
    if result.get("category"):
        updates["category"] = result["category"]
    if result.get("priority_score"):
        updates["priority"] = result["priority_score"]
    if result.get("sentiment"):
        updates["sentiment"] = result["sentiment"]
    if updates:
        db.update_email_fields(email_id, **updates)
    return jsonify(result)


@app.route("/api/thread/<thread_id>/first")
def api_thread_first(thread_id: str):
    emails = db.list_thread(thread_id)
    if not emails:
        return jsonify({"error": "Thread empty"}), 404
    return jsonify({"email_id": emails[0]["id"]})


@app.route("/api/thread/<thread_id>/analyze", methods=["POST"])
def api_analyze_thread(thread_id: str):
    emails = db.list_thread(thread_id)
    if not emails:
        return jsonify({"error": "Thread has no emails"}), 404
    try:
        result = llm_service.summarize_thread(emails)
    except llm_service.LLMError as e:
        return jsonify({"error": str(e)}), 500
    db.save_analysis(None, thread_id, "thread", result, llm_service.get_active_model())
    return jsonify(result)


@app.route("/api/email/<int:email_id>/draft-reply", methods=["POST"])
def api_draft_reply(email_id: int):
    email = db.get_email(email_id)
    if not email:
        return jsonify({"error": "Email not found"}), 404
    data = request.get_json(silent=True) or {}
    tone = data.get("tone", "professional")
    intent = data.get("intent", "acknowledge and respond helpfully")
    try:
        draft = llm_service.draft_reply(email, tone=tone, intent=intent)
        return jsonify({"draft": draft})
    except llm_service.LLMError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bulk-categorize", methods=["POST"])
def api_bulk_categorize():
    """Categorize any emails that don't yet have a category."""
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 15))
    emails = [e for e in db.list_emails(limit=200) if not e.get("category")][:limit]
    updated = 0
    errors = []
    for e in emails:
        try:
            cat, pri, sent = llm_service.categorize_email(e)
            db.update_email_fields(e["id"], category=cat, priority=pri, sentiment=sent)
            updated += 1
        except llm_service.LLMError as ex:
            errors.append(str(ex))
            break
    return jsonify({"updated": updated, "remaining": len([x for x in db.list_emails(limit=200) if not x.get("category")]),
                    "errors": errors[:3]})


# ---- Search ------------------------------------------------------------

@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    use_ai = bool(data.get("ai", False))
    if not query:
        return jsonify({"results": []})
    keyword = db.list_emails(limit=60, search=query)
    if use_ai and keyword:
        try:
            ranked_ids = llm_service.semantic_related_search(query, keyword, top_k=10)
            id_map = {e["id"]: e for e in keyword}
            results = [id_map[i] for i in ranked_ids if i in id_map]
            leftover = [e for e in keyword if e["id"] not in set(ranked_ids)]
            results.extend(leftover[: max(0, 10 - len(results))])
        except llm_service.LLMError:
            results = keyword[:10]
    else:
        results = keyword[:20]
    return jsonify({
        "results": [
            {
                "id": r["id"],
                "subject": r.get("subject", ""),
                "sender": r.get("sender", ""),
                "date": r.get("date", ""),
                "snippet": r.get("snippet", ""),
                "category": r.get("category", ""),
                "priority": r.get("priority", 0),
            }
            for r in results
        ]
    })


# ---- Chat --------------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400
    sid = session["sid"]

    contacts = db.list_contacts()
    # Get sender name from connected account
    sender_name = ""
    imap_creds = imap_service.get_credentials()
    if imap_creds:
        sender_name = imap_creds.get("display_name", "")
    if not sender_name and gmail_service.is_authenticated():
        try:
            profile = gmail_service.get_user_profile()
            sender_name = profile.get("emailAddress", "").split("@")[0].replace(".", " ").title()
        except Exception:
            pass
    intent_result = llm_service.detect_chat_intent(message, contacts, sender_name)
    intent = intent_result.get("intent", "question")

    if intent == "send_email" and intent_result.get("to_email"):
        to_email = intent_result["to_email"]
        subject = intent_result.get("subject", "")
        body = intent_result.get("body", "")
        to_name = intent_result.get("to_name", "")
        import re as _re
        if sender_name:
            body = _re.sub(r'\[Your Name\]|\[your name\]|\[Your name\]|\[YOUR NAME\]', sender_name, body)
        try:
            imap_service.send_message(to_email, subject, body)
            answer = f"Email sent successfully!\n\nTo: {to_name + ' - ' if to_name else ''}{to_email}\nSubject: {subject}\n\n{body}"
        except Exception as e:
            answer = f"Failed to send email: {e}"
        db.save_chat_message(sid, "user", message)
        db.save_chat_message(sid, "assistant", answer)
        return jsonify({"answer": answer, "referenced": []})

    if intent == "delete_email" and intent_result.get("email_id"):
        email_id = int(intent_result["email_id"])
        deleted = db.delete_email_by_id(email_id)
        answer = f"Email #{email_id} has been deleted." if deleted else f"Email #{email_id} not found."
        db.save_chat_message(sid, "user", message)
        db.save_chat_message(sid, "assistant", answer)
        return jsonify({"answer": answer, "referenced": []})

    candidates = db.list_emails(limit=40, search=message) or db.list_emails(limit=20)
    history = db.get_chat_history(sid)
    try:
        answer = llm_service.answer_question_about_emails(message, candidates, history)
    except llm_service.LLMError as e:
        return jsonify({"error": str(e)}), 500

    referenced = [c["id"] for c in candidates[:8]]
    db.save_chat_message(sid, "user", message)
    db.save_chat_message(sid, "assistant", answer, referenced)
    return jsonify({
        "answer": answer,
        "referenced": [
            {"id": c["id"], "subject": c.get("subject", ""), "sender": c.get("sender", "")}
            for c in candidates[:5]
        ],
    })


@app.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    db.clear_chat_history(session["sid"])
    return jsonify({"ok": True})


# ---- Contacts ----------------------------------------------------------

@app.route("/contacts")
def contacts_page():
    contacts = db.list_contacts()
    return render_template("contacts.html", contacts=contacts)


@app.route("/api/contacts", methods=["GET"])
def api_list_contacts():
    return jsonify({"contacts": db.list_contacts()})


@app.route("/api/contacts", methods=["POST"])
def api_add_contact():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email_addr = (data.get("email") or "").strip()
    if not name or not email_addr:
        return jsonify({"error": "Name and email are required"}), 400
    contact_id = db.add_contact(name, email_addr)
    return jsonify({"id": contact_id, "name": name, "email": email_addr})


@app.route("/api/contacts/<int:contact_id>", methods=["DELETE"])
def api_delete_contact(contact_id: int):
    db.delete_contact(contact_id)
    return jsonify({"ok": True})


# ---- Reports -----------------------------------------------------------

@app.route("/api/report/email/<int:email_id>", methods=["POST"])
def api_report_email(email_id: int):
    email = db.get_email(email_id)
    if not email:
        return jsonify({"error": "Email not found"}), 404
    analysis = db.get_analysis_for_email(email_id)
    if not analysis:
        try:
            result = llm_service.summarize_email(email)
        except llm_service.LLMError as e:
            return jsonify({"error": str(e)}), 500
        db.save_analysis(email_id, email.get("thread_id"), "email", result, llm_service.get_active_model())
        analysis = {
            "summary": result.get("summary", ""),
            "key_points": result.get("key_points", []),
            "action_items": result.get("action_items", []),
            "sentiment": result.get("sentiment", ""),
            "entities": result.get("entities", []),
            "metadata": result.get("metadata", {}),
        }
    path = pdf_generator.generate_email_report(email, analysis)
    report_id = db.save_report(
        f"Email: {email.get('subject', '')[:60]}", "email", str(path),
        {"email_id": email_id}, 1,
    )
    return jsonify({"report_id": report_id, "url": url_for("download_report", report_id=report_id)})


@app.route("/api/report/thread/<thread_id>", methods=["POST"])
def api_report_thread(thread_id: str):
    emails = db.list_thread(thread_id)
    if not emails:
        return jsonify({"error": "Thread empty"}), 404
    analysis = db.get_analysis_for_thread(thread_id)
    if not analysis:
        try:
            result = llm_service.summarize_thread(emails)
        except llm_service.LLMError as e:
            return jsonify({"error": str(e)}), 500
        db.save_analysis(None, thread_id, "thread", result, llm_service.get_active_model())
        analysis = result
    path = pdf_generator.generate_thread_report(thread_id, emails, analysis)
    report_id = db.save_report(
        f"Thread: {emails[0].get('subject', '')[:60]}", "thread", str(path),
        {"thread_id": thread_id}, len(emails),
    )
    return jsonify({"report_id": report_id, "url": url_for("download_report", report_id=report_id)})


@app.route("/api/report/related/<int:email_id>", methods=["POST"])
def api_report_related(email_id: int):
    """Generate a comprehensive report for an email and all related messages
    (by thread, then by subject/sender fallback)."""
    email = db.get_email(email_id)
    if not email:
        return jsonify({"error": "Email not found"}), 404

    thread = db.list_thread(email["thread_id"]) if email.get("thread_id") else [email]
    related = []
    if len(thread) <= 1:
        related = db.find_related_emails(email, limit=15)

    # Combine thread + related, deduplicated, sorted chronologically
    combined_map = {e["id"]: e for e in thread}
    for r in related:
        combined_map[r["id"]] = r
    combined = sorted(combined_map.values(), key=lambda x: x.get("date", ""))

    if not combined:
        return jsonify({"error": "No emails to summarize"}), 400

    try:
        result = llm_service.summarize_thread(combined)
    except llm_service.LLMError as e:
        return jsonify({"error": str(e)}), 500

    thread_id_for_save = email.get("thread_id") or f"related_{email_id}"
    db.save_analysis(None, thread_id_for_save, "thread", result, llm_service.get_active_model())

    path = pdf_generator.generate_thread_report(thread_id_for_save, combined, result)
    subject = email.get("subject", "")[:60]
    label = f"Thread: {subject}" if len(thread) > 1 else f"Related to: {subject}"
    report_id = db.save_report(label, "thread", str(path), {"seed_email_id": email_id}, len(combined))
    return jsonify({
        "report_id": report_id,
        "url": url_for("download_report", report_id=report_id),
        "email_count": len(combined),
    })


@app.route("/api/report/digest", methods=["POST"])
def api_report_digest():
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 40))
    title = data.get("title", "Executive Email Digest")
    emails = db.list_emails(limit=limit)
    if not emails:
        return jsonify({"error": "No emails to digest"}), 400
    try:
        digest = llm_service.generate_executive_digest(emails)
    except llm_service.LLMError as e:
        return jsonify({"error": str(e)}), 500
    stats = db.stats()
    path = pdf_generator.generate_digest_report(emails, digest, title=title, stats=stats)
    report_id = db.save_report(title, "digest", str(path), {"limit": limit}, len(emails))
    return jsonify({"report_id": report_id, "url": url_for("download_report", report_id=report_id)})


@app.route("/reports/<int:report_id>/download")
def download_report(report_id: int):
    report = db.get_report(report_id)
    if not report or not Path(report["file_path"]).exists():
        return "Report not found", 404
    return send_file(
        report["file_path"], as_attachment=True,
        download_name=f"{secure_filename(report['title'])}.pdf",
    )


@app.route("/api/report/<int:report_id>/delete", methods=["POST"])
def api_report_delete(report_id: int):
    report = db.get_report(report_id)
    if report:
        try:
            Path(report["file_path"]).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete_report(report_id)
    return jsonify({"ok": True})


# ---- Settings ---------------------------------------------------------

@app.route("/api/settings/model", methods=["POST"])
def api_set_model():
    data = request.get_json(silent=True) or {}
    model = data.get("model", "").strip()
    if not model:
        return jsonify({"error": "model required"}), 400
    llm_service.set_active_model(model)
    return jsonify({"ok": True, "model": model})


@app.route("/api/stats")
def api_stats():
    return jsonify({"stats": db.stats(), "timeline": db.timeline()})


@app.route("/api/export/csv")
def api_export_csv():
    """Export all emails as CSV."""
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "date", "sender", "sender_email", "subject", "category",
                "priority", "sentiment", "is_read", "snippet"])
    for e in db.list_emails(limit=10000):
        w.writerow([
            e["id"], e.get("date", ""), e.get("sender", ""), e.get("sender_email", ""),
            e.get("subject", ""), e.get("category", ""), e.get("priority", 0),
            e.get("sentiment", ""), e.get("is_read", 0),
            (e.get("snippet") or "").replace("\n", " ")[:200],
        ])
    from flask import Response
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=emails_export.csv"},
    )


# ---- Health -----------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "gmail_connected": gmail_service.is_authenticated()})


# ---- Init -------------------------------------------------------------

def main():
    db.init_db()
    print("=" * 60)
    print(f"  {config.SITE_NAME}")
    print("=" * 60)
    print(f"  Open in browser: {config.SITE_URL}")
    print(f"  Database:        {config.DATABASE_PATH}")
    print(f"  Reports folder:  {config.REPORTS_DIR}")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
