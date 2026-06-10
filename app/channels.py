"""Outbound channel adapters: Telegram, Resend email, Slack alerts.

All senders are best-effort — failures are trace-logged, never raised,
so a missing key or provider outage can't break the pipeline.
"""
import requests

from . import config
from .trace import bus

TIMEOUT = 10


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------

def send_telegram(chat_id: str | int, text: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=TIMEOUT,
        )
        return r.ok
    except Exception:
        return False


def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    """Send via Resend. Returns (ok, detail)."""
    if not config.RESEND_API_KEY:
        return False, "RESEND_API_KEY not configured"
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
            json={"from": config.EMAIL_FROM, "to": [to],
                  "subject": subject, "text": body},
            timeout=TIMEOUT,
        )
        if r.ok:
            return True, f"Resend id {r.json().get('id', '?')}"
        return False, f"Resend {r.status_code}: {r.text[:160]}"
    except Exception as exc:
        return False, str(exc)[:160]


def notify_slack(text: str) -> bool:
    if not config.SLACK_WEBHOOK_URL:
        return False
    try:
        return requests.post(config.SLACK_WEBHOOK_URL, json={"text": text},
                             timeout=TIMEOUT).ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Dispatch — the one place that turns an approved/auto-handled draft
# into a real outbound message on the item's channel.
# ---------------------------------------------------------------------------

def dispatch_reply(item: dict) -> None:
    """Send the drafted reply back out on the channel the item arrived on."""
    item_id, payload, draft = item["id"], item["payload"], item.get("draft")
    if not draft:
        return

    if item["kind"] == "telegram" and payload.get("chat_id"):
        ok = send_telegram(payload["chat_id"], draft)
        bus.emit(item_id, "Channel: Telegram",
                 "Reply delivered to Telegram chat" if ok else "Telegram send failed",
                 f"chat_id={payload['chat_id']}")
        return

    to = payload.get("email")
    if to:
        subject = "Re: " + (payload.get("subject") or "your inquiry")
        ok, detail = send_email(to, subject, draft)
        bus.emit(item_id, "Channel: Email",
                 f"Reply emailed to {to}" if ok else "Email not sent (simulated send)",
                 detail)


def alert_hot_lead(item_id: str, state: dict) -> None:
    """Slack alert for hot leads / high-risk items at routing time."""
    if not config.SLACK_WEBHOOK_URL:
        return
    name = state.get("name") or "Anonymous"
    why = (f"score {state.get('score')}/100 ({state.get('priority')})"
           if state.get("priority") == "hot" else f"risk: {state.get('risk_level')}")
    ok = notify_slack(
        f":rotating_light: *Attention needed* — {name} ({state.get('company') or state.get('email') or 'n/a'})\n"
        f"> {state.get('summary') or ''}\n_{why}_ · review in the Command Center")
    if ok:
        bus.emit(item_id, "Channel: Slack", "Team alerted in Slack", why)
