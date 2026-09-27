# Mail Agent — AI Email Intelligence Platform

An AI-powered email intelligence web application built with Flask and LLMs (via OpenRouter). Connects to your Gmail inbox, analyzes and summarizes emails using generative AI, drafts and sends replies through natural language chat commands, and generates professional PDF reports — all from a single local interface.

> **Course:** 25ARE471 — Introduction to Generative AI  
> **Student:** Kevin Biju (CB.EN.U4ARE23022)  
> **Institution:** Amrita Vishwa Vidyapeetham

---

## Features

### Email Management
- Gmail integration via IMAP App Password or Google OAuth 2.0
- Local SQLite storage with full email content
- Thread grouping and conversation reconstruction (References/In-Reply-To chain parsing)
- Gmail-style search with operators (`from:`, `to:`, `subject:`, `is:unread`, `has:attachment`, etc.)
- CSV export of all emails

### AI Intelligence (LLM-powered via OpenRouter)
- **Single-email analysis:** summary, key points, action items, sentiment, priority scoring, entity extraction
- **Thread summarization:** decisions made, open questions, timeline, participant analysis
- **Bulk auto-categorization:** work, personal, finance, travel, shopping, promotional, etc.
- **Reply drafting:** with tone control (professional, friendly, formal, brief, apologetic)
- **Executive digest:** themes, priorities, insights, and recommended actions across your inbox
- **Natural-language chat:** ask questions about your emails and get grounded, cited answers
- **AI-ranked semantic search:** LLM re-ranks keyword results by relevance
- **Email sending via chat:** say "send a mail to mom saying I'll be late" and it drafts and sends
- **Email deletion via chat:** say "delete email #5" to remove emails conversationally
- **Multi-model support:** GPT-4o, GPT-4o mini, Claude 3.5, Gemini 1.5, Llama 3.1, Gemma 2

### Contacts
- Add contacts with nicknames (e.g. "Mom — mom@gmail.com")
- AI chat resolves contact names automatically when sending emails

### Voice Commands
- Built-in voice input via Web Speech API
- Click the microphone button in AI Chat to speak your command

### Reports
- Individual email PDF reports with full AI analysis
- Thread analysis PDF with timeline and message-by-message breakdown
- Executive digest PDF with metrics, themes, and email index
- Branded ReportLab design, stored locally for download

### User Experience
- Modern responsive UI with dark and light themes
- Live toast notifications and inline loading states
- Analytics dashboard: volume trends, category distribution, top correspondents
- One-click launch on Windows (`launch.bat`)

---

## Screenshots

| Dashboard | AI Chat | Contacts |
|-----------|---------|----------|
| Analytics overview with email volume, categories, top senders | Send emails, delete emails, ask questions — all via natural language | Manage contacts for quick email sending |

---

## Quick Start

### One-Click Launch (Windows)

Double-click **`launch.bat`**. It will:
1. Verify Python 3.10+ is installed
2. Create a virtual environment (first run only)
3. Install all dependencies (first run only)
4. Start the Flask server on `http://localhost:5000`
5. Open your browser automatically

Press `Ctrl+C` to stop the server.

### Manual Launch

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

---

## Connecting Your Email

### Option A: App Password (Recommended — 30 seconds)

Works with Gmail, Outlook, Yahoo, iCloud, or any custom IMAP provider.

**For Gmail:**
1. Enable **2-Step Verification** on your Google account
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
3. Enter any app name (e.g. "Mail Agent"), click **Create**
4. Copy the 16-character password
5. In the app: **Settings** → enter your name, email, and app password → **Connect**

### Option B: Google OAuth (Advanced)

Only needed for Gmail API access. Requires a Google Cloud Project:
1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create a project and enable the **Gmail API**
3. Configure OAuth consent screen (External, Testing)
4. Create OAuth Client ID → Web application → redirect URI: `http://localhost:5000/oauth/callback`
5. In the app: **Settings** → **OAuth** tab → upload the JSON

### Demo Mode

Click **Load Demo Data** on the dashboard — 15 realistic sample emails are included so you can explore every feature without connecting an account.

---

## Project Structure

```
mail-agent/
├── launch.bat              # One-click Windows launcher
├── app.py                  # Flask application (all routes)
├── config.py               # Configuration & constants
├── requirements.txt        # Python dependencies
├── .gitignore
├── services/
│   ├── database.py         # SQLite layer (emails, analyses, reports, chat, contacts)
│   ├── gmail_service.py    # Gmail OAuth integration
│   ├── imap_service.py     # IMAP/SMTP email fetching & sending
│   ├── llm_service.py      # OpenRouter LLM integration & prompts
│   ├── pdf_generator.py    # ReportLab PDF report templates
│   └── demo_data.py        # Sample data for demo mode
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Layout with sidebar navigation
│   ├── index.html          # Dashboard
│   ├── emails.html         # Email list with search
│   ├── email_detail.html   # Single email view + analysis
│   ├── threads.html        # Thread listing
│   ├── chat.html           # AI Chat with voice input
│   ├── contacts.html       # Contact management
│   ├── analytics.html      # Charts and stats
│   ├── reports.html        # Generated reports
│   └── settings.html       # Account & model configuration
├── static/
│   ├── css/style.css       # Full stylesheet (dark/light themes)
│   └── js/app.js           # Client-side utilities
├── data/                   # SQLite database (auto-created)
├── credentials/            # OAuth tokens (auto-created)
└── reports/                # Generated PDF reports
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.10+, Flask 3 |
| **Database** | SQLite (zero-setup, single file) |
| **LLM** | OpenRouter API (multi-model gateway) |
| **Email** | IMAP/SMTP with App Password, Google OAuth 2.0 |
| **PDF** | ReportLab |
| **Voice** | Web Speech API (browser-native) |
| **Frontend** | Vanilla JS + CSS (no build step) |

---

## Configuration

- **Default LLM:** `openai/gpt-4o-mini` — change in **Settings → AI Model**
- **API Key:** Set the `OPENROUTER_API_KEY` environment variable before launching, or edit `config.py`. Get a free key at [openrouter.ai](https://openrouter.ai/).
- **Port:** Defaults to `5000`. On macOS, the bundled version auto-selects an available port.

---

## Key Technical Highlights

- **Thread reconstruction** without native Gmail thread API — uses References/In-Reply-To header chain parsing with subject normalization fallback
- **Hallucination control** via retrieval-grounded prompting with mandatory email citations
- **Intent detection** in chat — LLM classifies user messages as questions, send-email commands, or delete-email commands
- **Server-side name replacement** ensures email sign-offs always use the user's real name, never LLM placeholders
- **Schema-constrained JSON output** for structured AI analysis results
- **Graceful degradation** — works with free LLM models, falls back automatically on API errors

---

## License

This project was built as an academic submission for 25ARE471 (Introduction to Generative AI) at Amrita Vishwa Vidyapeetham.
