"""Telegram intake.

Two modes, chosen automatically:
- BASE_URL set (deployed): webhook mode — Telegram POSTs updates to /api/telegram/webhook.
- No BASE_URL (localhost): long-polling background thread via getUpdates.
"""
import threading

import requests

from . import channels, config, db
from .trace import bus

API = "https://api.telegram.org/bot{token}/{method}"
_bot_username: str | None = None
_started = False


def bot_username() -> str | None:
    global _bot_username
    if _bot_username is None and config.TELEGRAM_BOT_TOKEN:
        try:
            r = requests.get(API.format(token=config.TELEGRAM_BOT_TOKEN, method="getMe"),
                             timeout=10).json()
            _bot_username = r.get("result", {}).get("username")
        except Exception:
            pass
    return _bot_username


def handle_update(update: dict, run_pipeline) -> str | None:
    """Process one Telegram update. Returns the new item_id (or None if ignored)."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or not msg.get("text"):
        return None
    chat_id = msg["chat"]["id"]
    text = msg["text"].strip()
    frm = msg.get("from", {})
    name = " ".join(p for p in (frm.get("first_name"), frm.get("last_name")) if p) or "Telegram user"

    if text.startswith("/start"):
        channels.send_telegram(chat_id,
                      "👋 Hi! I'm the AI Automation Command Center demo.\n\n"
                      "Send me any business message — e.g. \"We need a demo, budget approved, "
                      "urgent\" — and a team of AI agents will triage it, score it, draft a reply, "
                      "and route it for approval. You'll get the reply right here.\n\n"
                      "Watch the agents reason live on the dashboard!")
        return None

    payload = {"name": name, "username": frm.get("username", ""),
               "chat_id": chat_id, "message": text}
    item_id = db.create_item("telegram", payload)
    bus.emit(item_id, "Intake", "New Telegram message",
             f"{name} (@{frm.get('username') or 'n/a'})")
    channels.send_telegram(chat_id, "✅ Got it — our AI agents are processing your message. "
                                    "You'll receive a reply here shortly.")
    threading.Thread(target=run_pipeline, args=(item_id, "telegram", payload),
                     daemon=True).start()
    return item_id


def set_webhook() -> bool:
    if not (config.TELEGRAM_BOT_TOKEN and config.BASE_URL):
        return False
    try:
        return requests.get(
            API.format(token=config.TELEGRAM_BOT_TOKEN, method="setWebhook"),
            params={"url": f"{config.BASE_URL}/api/telegram/webhook"},
            timeout=10).json().get("ok", False)
    except Exception:
        return False


def _poll_loop(run_pipeline) -> None:
    offset = 0
    # ensure no webhook is set, otherwise getUpdates returns 409
    try:
        requests.get(API.format(token=config.TELEGRAM_BOT_TOKEN, method="deleteWebhook"),
                     timeout=10)
    except Exception:
        pass
    while True:
        try:
            r = requests.get(
                API.format(token=config.TELEGRAM_BOT_TOKEN, method="getUpdates"),
                params={"offset": offset, "timeout": 25},
                timeout=35).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                handle_update(update, run_pipeline)
        except Exception:
            import time
            time.sleep(5)


def start(run_pipeline) -> str:
    """Activate Telegram intake. Returns a human-readable mode string."""
    global _started
    if not config.TELEGRAM_BOT_TOKEN:
        return "disabled"
    if _started:
        return "already-started"
    _started = True
    if config.BASE_URL:
        return "webhook" if set_webhook() else "webhook-setup-failed"
    threading.Thread(target=_poll_loop, args=(run_pipeline,), daemon=True).start()
    return "polling"
