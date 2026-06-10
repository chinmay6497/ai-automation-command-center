"""Seed demo data so the dashboard is never empty on first load."""
import json
import time

from . import db

DEMO_ITEMS = [
    {
        "kind": "lead",
        "payload": {"name": "Sarah Mitchell", "email": "sarah@apexlogistics.com",
                    "company": "Apex Logistics",
                    "message": "We need to automate our invoice processing urgently — budget "
                               "approved for this quarter. Can we see a demo this week?"},
        "status": "pending_approval", "classification": "purchase_intent", "score": 92,
        "priority": "hot",
        "summary": "Enterprise logistics firm with approved budget wants invoice automation demo this week.",
        "draft": "Hi Sarah,\n\nThanks for reaching out — invoice automation is exactly what we do "
                 "best. Since your timeline is this week, I've held two demo slots: Tue 2pm and "
                 "Wed 10am ET. Pick whichever suits, or grab any time here: [calendar].\n\n"
                 "Looking forward to it,\nSales Team",
        "risk_level": "low", "risk_notes": "No compliance flags detected.",
        "engine": "groq", "duration_ms": 4180,
    },
    {
        "kind": "email",
        "payload": {"name": "Dev Patel", "email": "dev.p@gmail.com",
                    "subject": "Question about integrations",
                    "body": "Hi, curious whether your platform integrates with HubSpot. "
                            "Just evaluating options for next year."},
        "status": "auto_handled", "classification": "information_request", "score": 44,
        "priority": "warm",
        "summary": "Prospect evaluating options asks about HubSpot integration; no near-term timeline.",
        "draft": "Hi Dev,\n\nGreat question — yes, we offer a native HubSpot integration "
                 "(contacts, deals, and timeline events sync both ways). I've attached a short "
                 "overview. Happy to walk you through it whenever your evaluation kicks off.\n\n"
                 "Best,\nSales Team",
        "risk_level": "low", "risk_notes": "No compliance flags detected.",
        "engine": "groq", "duration_ms": 3650,
    },
    {
        "kind": "email",
        "payload": {"name": "M. Okafor", "email": "m.okafor@vertexcorp.io",
                    "subject": "Service cancellation and refund",
                    "body": "We have had repeated outages and are considering cancelling our "
                            "contract. Please advise on the refund process before we involve legal."},
        "status": "pending_approval", "classification": "complaint_or_risk", "score": 38,
        "priority": "cold",
        "summary": "Existing customer threatening cancellation and legal action over outages; requests refund process.",
        "draft": "Hi,\n\nI'm sorry about the disruption you've experienced — that's not the "
                 "standard we hold ourselves to. I've escalated this to our reliability team and "
                 "our account director will call you today to discuss remediation and your "
                 "options, including the refund process.\n\nSincerely,\nSupport Leadership",
        "risk_level": "high", "risk_notes": "Flagged terms: cancel, refund, legal. Churn + legal risk.",
        "engine": "groq", "duration_ms": 4920,
    },
]

DEMO_TRACES = [
    ("Intake Guard", "Validating inbound payload", "Payload OK"),
    ("Triage Agent", "Intent classified", "See item summary"),
    ("Scoring Agent", "Lead scored", "Signals weighed: urgency, budget, fit"),
    ("Drafting Agent", "Draft ready", "Personalized reply generated"),
    ("Compliance Agent", "Risk & policy check", "See risk notes"),
    ("Routing Agent", "Routing decision", "Threshold + risk based"),
]


def seed_if_empty() -> None:
    conn = db.get_conn()
    if conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] > 0:
        return
    now = time.time()
    for i, demo in enumerate(DEMO_ITEMS):
        item_id = db.create_item(demo["kind"], demo["payload"])
        db.update_item(
            item_id,
            status=demo["status"], classification=demo["classification"],
            score=demo["score"], priority=demo["priority"], summary=demo["summary"],
            draft=demo["draft"], risk_level=demo["risk_level"], risk_notes=demo["risk_notes"],
            engine=demo["engine"], created_at=now - 3600 * (i + 1),
            completed_at=now - 3600 * (i + 1) + demo["duration_ms"] / 1000,
            duration_ms=demo["duration_ms"],
        )
        for agent, title, detail in DEMO_TRACES:
            db.add_trace(item_id, agent, title, detail)
