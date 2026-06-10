"""Central configuration for the AI Automation Command Center."""
import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY") or None
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
DB_PATH: str = os.getenv("DB_PATH", "command_center.db")
APP_NAME = "AI Automation Command Center"
VERSION = "1.1.0"

# Leads scoring at or above this go to the human approval queue before any reply is "sent".
APPROVAL_SCORE_THRESHOLD = int(os.getenv("APPROVAL_SCORE_THRESHOLD", "70"))

# ---------------------------------------------------------------------------
# Channel integrations (all optional — features activate when keys are present)
# ---------------------------------------------------------------------------

# Telegram bot (create via @BotFather). Inbound DMs + outbound replies.
TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN") or None
# Public base URL of this deployment (e.g. https://myapp.onrender.com).
# If set, Telegram uses webhook mode; if empty, long-polling (works on localhost).
BASE_URL: str | None = (os.getenv("BASE_URL") or "").rstrip("/") or None

# Resend (https://resend.com) — real outbound email on approval.
RESEND_API_KEY: str | None = os.getenv("RESEND_API_KEY") or None
EMAIL_FROM: str = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

# Slack incoming webhook — instant hot-lead / high-risk alerts.
SLACK_WEBHOOK_URL: str | None = os.getenv("SLACK_WEBHOOK_URL") or None

# Optional API key for machine-to-machine intake (n8n / Zapier / Make).
# When set, POST /api/leads and /api/emails require header  X-API-Key: <value>
# from external callers. The built-in dashboard and contact page stay open.
INTAKE_API_KEY: str | None = os.getenv("INTAKE_API_KEY") or None
