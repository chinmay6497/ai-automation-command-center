"""FastAPI app: REST API + SSE streams + channel integrations + static pages.

Part of the AI Automation Command Center demo by Chinmay Raval.
"""
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from . import channels, config, db, telegram_bot
from .graph import run_pipeline
from .seed import seed_if_empty
from .trace import bus

app = FastAPI(title=config.APP_NAME, version=config.VERSION,
              docs_url=None, redoc_url=None)  # /docs replaced by dark-themed version below

DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>API Docs — AI Automation Command Center</title>
<link rel="icon" href="/static/logo.svg" type="image/svg+xml">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<style>
  html { filter: invert(0.92) hue-rotate(180deg); background: #111722; }
  img, .swagger-ui .info .title small svg { filter: invert(1) hue-rotate(180deg); }
  body { margin: 0; }
  .back-bar { position: sticky; top: 0; z-index: 50; padding: 10px 20px;
    background: #e6e9ef; border-bottom: 1px solid #cfd6e4;
    font-family: ui-sans-serif, system-ui, sans-serif; font-size: 14px; }
  .back-bar a { color: #0b5cad; text-decoration: none; font-weight: 600; margin-right: 18px; }
  .back-bar a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="back-bar">
  <a href="/">&larr; Back to dashboard</a>
  <a href="/contact">Contact demo</a>
  <a href="/integrations">Integrations</a>
</div>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({ url: "/openapi.json", dom_id: "#swagger-ui",
                  presets: [SwaggerUIBundle.presets.apis], deepLinking: true });
</script>
</body>
</html>"""


@app.get("/docs", include_in_schema=False)
def docs_page():
    return HTMLResponse(DOCS_HTML)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
TELEGRAM_MODE = "disabled"


@app.on_event("startup")
def _startup() -> None:
    global TELEGRAM_MODE
    db.get_conn()
    seed_if_empty()
    TELEGRAM_MODE = telegram_bot.start(run_pipeline)


class LeadIn(BaseModel):
    name: str = Field("", max_length=120)
    email: str = Field("", max_length=200)
    company: str = Field("", max_length=200)
    message: str = Field(..., min_length=3, max_length=4000)


class EmailIn(BaseModel):
    name: str = Field("", max_length=120)
    email: str = Field("", max_length=200)
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=3, max_length=4000)


class Decision(BaseModel):
    note: str = Field("", max_length=500)


def _check_intake_auth(request: Request) -> None:
    """If INTAKE_API_KEY is set, require it from machine callers (n8n/Zapier/curl).

    Same-origin browser requests (the dashboard and contact page) stay open —
    browsers send Sec-Fetch-Site: same-origin, automation tools don't.
    """
    if not config.INTAKE_API_KEY:
        return
    if request.headers.get("sec-fetch-site") == "same-origin":
        return
    if request.headers.get("x-api-key") != config.INTAKE_API_KEY:
        raise HTTPException(401, "Missing or invalid X-API-Key header")


async def _process(item_id: str, kind: str, payload: dict) -> None:
    try:
        await asyncio.to_thread(run_pipeline, item_id, kind, payload)
    except Exception:
        pass  # already recorded as failed + traced


@app.post("/api/leads", status_code=202)
async def submit_lead(lead: LeadIn, request: Request):
    _check_intake_auth(request)
    item_id = db.create_item("lead", lead.model_dump())
    bus.emit(item_id, "Intake", "New lead received",
             f"{lead.name or 'Anonymous'} ({lead.company or 'no company'})")
    asyncio.create_task(_process(item_id, "lead", lead.model_dump()))
    return {"item_id": item_id, "status": "processing"}


@app.post("/api/emails", status_code=202)
async def submit_email(email: EmailIn, request: Request):
    _check_intake_auth(request)
    item_id = db.create_item("email", email.model_dump())
    bus.emit(item_id, "Intake", "New email received", email.subject or "(no subject)")
    asyncio.create_task(_process(item_id, "email", email.model_dump()))
    return {"item_id": item_id, "status": "processing"}


@app.post("/api/telegram/webhook")
async def telegram_webhook(update: dict):
    item_id = await asyncio.to_thread(telegram_bot.handle_update, update, run_pipeline)
    return {"ok": True, "item_id": item_id}


@app.get("/api/items")
def get_items(limit: int = 50):
    return db.list_items(min(limit, 200))


@app.get("/api/items/{item_id}")
def get_item(item_id: str):
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@app.post("/api/items/{item_id}/approve")
async def approve_item(item_id: str, decision: Decision = Decision()):
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item["status"] != "pending_approval":
        raise HTTPException(409, f"Item is '{item['status']}', not pending approval")
    db.update_item(item_id, status="approved")
    bus.emit(item_id, "Human Reviewer", "Reply APPROVED",
             decision.note or "Approved from dashboard")
    await asyncio.to_thread(channels.dispatch_reply, item)
    return {"item_id": item_id, "status": "approved"}


@app.post("/api/items/{item_id}/reject")
def reject_item(item_id: str, decision: Decision = Decision()):
    item = db.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item["status"] != "pending_approval":
        raise HTTPException(409, f"Item is '{item['status']}', not pending approval")
    db.update_item(item_id, status="rejected")
    bus.emit(item_id, "Human Reviewer", "Reply REJECTED",
             decision.note or "Rejected from dashboard")
    return {"item_id": item_id, "status": "rejected"}


@app.get("/api/metrics")
def get_metrics():
    return db.metrics()


@app.get("/api/config")
def get_app_config():
    """Which channels are live — drives the dashboard's integration cards."""
    return {
        "engine": "groq" if config.GROQ_API_KEY else "heuristic-fallback",
        "telegram": {"enabled": bool(config.TELEGRAM_BOT_TOKEN), "mode": TELEGRAM_MODE,
                     "bot_username": telegram_bot.bot_username()},
        "email_out": bool(config.RESEND_API_KEY),
        "slack_alerts": bool(config.SLACK_WEBHOOK_URL),
        "intake_protected": bool(config.INTAKE_API_KEY),
        "version": config.VERSION,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "version": config.VERSION,
            "engine": "groq" if config.GROQ_API_KEY else "heuristic-fallback"}


@app.get("/api/stream")
async def stream_all():
    """Global SSE feed of every agent trace event (powers the live activity feed)."""
    q = bus.subscribe("*")

    async def gen():
        try:
            while True:
                try:
                    yield {"data": await asyncio.wait_for(q.get(), timeout=25)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "keepalive"}
        finally:
            bus.unsubscribe("*", q)

    return EventSourceResponse(gen())


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/contact", include_in_schema=False)
    def contact():
        return FileResponse(FRONTEND_DIR / "contact.html")

    @app.get("/integrations", include_in_schema=False)
    def integrations():
        return FileResponse(FRONTEND_DIR / "integrations.html")
