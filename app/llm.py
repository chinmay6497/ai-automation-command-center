"""LLM access layer.

Primary engine: Groq (llama-3.3-70b) via langchain_groq.
Fallback engine: deterministic heuristics — the public demo must never 500
because of a missing key, rate limit, or provider outage.
"""
import json
import re

from . import config

_chat = None


def _get_chat():
    global _chat
    if _chat is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq

        _chat = ChatGroq(
            model=config.GROQ_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.2,
            max_tokens=1024,
        )
    return _chat


def llm_json(system: str, user: str) -> dict | None:
    """Call Groq and parse a JSON object out of the reply. None => caller should fall back."""
    chat = _get_chat()
    if chat is None:
        return None
    try:
        reply = chat.invoke(
            [("system", system + " Respond ONLY with a single JSON object."), ("user", user)]
        ).content
        match = re.search(r"\{.*\}", reply, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Heuristic fallback engine
# ---------------------------------------------------------------------------

HOT_SIGNALS = ["budget", "urgent", "asap", "enterprise", "demo", "pricing", "buy", "contract",
               "deadline", "immediately", "this week", "decision"]
WARM_SIGNALS = ["interested", "learn more", "curious", "evaluate", "compare", "question",
                "how does", "trial"]
RISK_SIGNALS = ["refund", "lawsuit", "legal", "angry", "cancel", "complaint", "gdpr",
                "data breach", "security incident"]


def heuristic_triage(text: str) -> dict:
    t = text.lower()
    if any(s in t for s in RISK_SIGNALS):
        intent = "complaint_or_risk"
    elif any(s in t for s in HOT_SIGNALS):
        intent = "purchase_intent"
    elif any(s in t for s in WARM_SIGNALS):
        intent = "information_request"
    else:
        intent = "general_inquiry"
    return {"intent": intent,
            "summary": (text[:140] + "…") if len(text) > 140 else text}


def heuristic_score(text: str) -> dict:
    t = text.lower()
    score = 35
    score += 12 * sum(1 for s in HOT_SIGNALS if s in t)
    score += 5 * sum(1 for s in WARM_SIGNALS if s in t)
    score = max(5, min(score, 98))
    priority = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
    return {"score": score, "priority": priority,
            "reasoning": "Keyword-signal scoring (fallback engine): "
                         f"{sum(1 for s in HOT_SIGNALS if s in t)} buying signals, "
                         f"{sum(1 for s in WARM_SIGNALS if s in t)} interest signals."}


def heuristic_draft(name: str, text: str, priority: str) -> dict:
    first = (name.split()[0] if name else "there")
    if priority == "hot":
        body = (f"Hi {first},\n\nThanks for reaching out — happy to help right away. "
                "Based on your message, the fastest next step is a short call so we can scope "
                "your requirements and timeline. Here's my calendar link: [calendar]. "
                "If easier, reply with two times that suit you.\n\nBest regards,\nSales Team")
    else:
        body = (f"Hi {first},\n\nThanks for your interest! I've attached an overview that "
                "answers the most common questions. If you'd like a walkthrough, just reply "
                "to this email and we'll set something up.\n\nBest regards,\nSales Team")
    return {"draft": body, "tone": "professional"}


def heuristic_risk(text: str) -> dict:
    t = text.lower()
    hits = [s for s in RISK_SIGNALS if s in t]
    level = "high" if hits else "low"
    return {"risk_level": level,
            "notes": f"Flagged terms: {', '.join(hits)}" if hits else "No compliance flags detected."}
