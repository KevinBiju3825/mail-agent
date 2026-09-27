"""Central configuration for the AI Email Intelligence Platform."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- OpenRouter (LLM) ---------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Default model - flexible and fast. Users can change from settings.
DEFAULT_MODEL = "openai/gpt-4o-mini"
FALLBACK_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
SITE_URL = "http://localhost:5000"
SITE_NAME = "Mail Agent"

# --- Gmail OAuth --------------------------------------------------------
CREDENTIALS_DIR = BASE_DIR / "credentials"
CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "client_secret.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]
OAUTH_REDIRECT_URI = "http://localhost:5000/oauth/callback"

# --- Database -----------------------------------------------------------
DATABASE_PATH = BASE_DIR / "data" / "emails.db"
REPORTS_DIR = BASE_DIR / "reports"

# --- Flask --------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
SESSION_TYPE = "filesystem"
SESSION_FILE_DIR = str(BASE_DIR / "data" / "sessions")

# --- Application --------------------------------------------------------
DEFAULT_FETCH_LIMIT = 50
MAX_FETCH_LIMIT = 500

# Allow HTTP for local OAuth (localhost only)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# Ensure directories exist
CREDENTIALS_DIR.mkdir(exist_ok=True)
(BASE_DIR / "data").mkdir(exist_ok=True)
(BASE_DIR / "data" / "sessions").mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
