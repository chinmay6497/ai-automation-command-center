"""Agent nodes for the LangGraph pipeline.

Each node receives the shared PipelineState, emits trace events to the bus,
and returns a partial state update. Every node tries Groq first and falls
back to the deterministic heuristic engine so the demo always completes.
"""
from typing import TypedDict

from . import config, llm
from .trace import bus


class PipelineState(TypedDict, total=False):
    item_id: str
    kind: str            # lead | email
    name: str
    email: str
    company: str
    text: str            # message body
    subject: str
    intent: str
    summary: str
    score: int
    priority: str
    score_reasoning: str
    draft: str
    risk_level: str
    risk_notes: str
    engine: str          # groq | heuristic-fallback
    route: str           # pending_approval | auto_handled


def _text(state: PipelineState) -> str:
    parts = [state.get("subject", ""), state.get("text", "")]
    return " — ".join(p for p in parts if p)


def intake_guard(state: PipelineState) -> dict:
    bus.emit(state["item_id"], "Intake Guard", "Validating inbound payload",
             f"kind={state['kind']}, from={state.get('email') or 'unknown'}")
    issues = []
    if not state.get("text"):
        issues.append("empty message body")
    if state["kind"] == "lead" and not state.get("email"):
        issues.append("missing contact email")
    detail = "Payload OK" if not issues else "Soft warnings: " + ", ".join(issues)
    bus.emit(state["item_id"], "Intake Guard", "Validation complete", detail)
    return {}


def triage_agent(state: PipelineState) -> dict:
    bus.emit(state["item_id"], "Triage Agent", "Classifying intent",
             "Analyzing message content and signals…")
    result = llm.llm_json(
        "You are a triage agent for a sales/support inbox. Classify the message. "
        'Return {"intent": "purchase_intent|information_request|complaint_or_risk|general_inquiry", '
        '"summary": "<one-sentence summary>"}',
        _text(state),
    )
    engine = "groq"
    if result is None or "intent" not in result:
        result, engine = llm.heuristic_triage(_text(state)), "heuristic-fallback"
    bus.emit(state["item_id"], "Triage Agent", f"Intent: {result['intent']}",
             result.get("summary", ""))
    return {"intent": result["intent"], "summary": result.get("summary", ""), "engine": engine}


def scoring_agent(state: PipelineState) -> dict:
    bus.emit(state["item_id"], "Scoring Agent", "Scoring lead quality",
             "Weighing buying signals, urgency, and fit…")
    result = llm.llm_json(
        "You are a lead-scoring agent. Score this inbound message 0-100 for sales priority. "
        '70+ = hot, 40-69 = warm, <40 = cold. Return {"score": <int>, '
        '"priority": "hot|warm|cold", "reasoning": "<brief>"}',
        f"Intent: {state.get('intent')}\nCompany: {state.get('company') or 'n/a'}\n"
        f"Message: {_text(state)}",
    )
    engine = state.get("engine", "groq")
    if result is None or "score" not in result:
        result, engine = llm.heuristic_score(_text(state)), "heuristic-fallback"
    score = int(result["score"])
    priority = result.get("priority") or ("hot" if score >= 70 else "warm" if score >= 40 else "cold")
    bus.emit(state["item_id"], "Scoring Agent", f"Score: {score}/100 → {priority.upper()}",
             result.get("reasoning", ""))
    return {"score": score, "priority": priority,
            "score_reasoning": result.get("reasoning", ""), "engine": engine}


def drafting_agent(state: PipelineState) -> dict:
    bus.emit(state["item_id"], "Drafting Agent", "Writing personalized reply",
             f"Tone calibrated for {state.get('priority', 'warm')} priority…")
    result = llm.llm_json(
        "You are an email-drafting agent. Write a short, warm, professional reply "
        "(under 120 words) to this inbound message. Personalize with the sender's name "
        'if known. Return {"draft": "<email body>"}',
        f"Sender: {state.get('name') or 'unknown'}\nPriority: {state.get('priority')}\n"
        f"Intent: {state.get('intent')}\nMessage: {_text(state)}",
    )
    engine = state.get("engine", "groq")
    if result is None or "draft" not in result:
        result = llm.heuristic_draft(state.get("name", ""), _text(state),
                                     state.get("priority", "warm"))
        engine = "heuristic-fallback"
    preview = result["draft"][:160] + ("…" if len(result["draft"]) > 160 else "")
    bus.emit(state["item_id"], "Drafting Agent", "Draft ready", preview)
    return {"draft": result["draft"], "engine": engine}


def compliance_agent(state: PipelineState) -> dict:
    bus.emit(state["item_id"], "Compliance Agent", "Risk & policy check",
             "Scanning for legal, churn, and data-privacy flags…")
    result = llm.llm_json(
        "You are a compliance agent. Assess risk in this message (legal threats, churn risk, "
        'privacy/GDPR issues, security incidents). Return {"risk_level": "low|medium|high", '
        '"notes": "<brief>"}',
        _text(state),
    )
    if result is None or "risk_level" not in result:
        result = llm.heuristic_risk(_text(state))
    bus.emit(state["item_id"], "Compliance Agent",
             f"Risk level: {result['risk_level'].upper()}", result.get("notes", ""))
    return {"risk_level": result["risk_level"], "risk_notes": result.get("notes", "")}


def routing_agent(state: PipelineState) -> dict:
    needs_human = (
        state.get("score", 0) >= config.APPROVAL_SCORE_THRESHOLD
        or state.get("risk_level") in ("medium", "high")
        or state.get("intent") == "complaint_or_risk"
    )
    route = "pending_approval" if needs_human else "auto_handled"
    reason = ("High-value or elevated-risk item — queued for human approval before send."
              if needs_human else
              "Routine item — reply auto-handled, logged to audit trail.")
    bus.emit(state["item_id"], "Routing Agent",
             "→ Human approval queue" if needs_human else "→ Auto-handled", reason)
    return {"route": route}
