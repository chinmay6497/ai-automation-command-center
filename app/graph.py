"""LangGraph wiring: intake → triage → score → draft → compliance → route."""
import time

from langgraph.graph import END, START, StateGraph

from . import channels, db
from .agents import (PipelineState, compliance_agent, drafting_agent, intake_guard,
                     routing_agent, scoring_agent, triage_agent)
from .trace import bus


def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("intake_guard", intake_guard)
    g.add_node("triage", triage_agent)
    g.add_node("score", scoring_agent)
    g.add_node("draft", drafting_agent)
    g.add_node("compliance", compliance_agent)
    g.add_node("route", routing_agent)

    g.add_edge(START, "intake_guard")
    g.add_edge("intake_guard", "triage")
    g.add_edge("triage", "score")
    g.add_edge("score", "draft")
    g.add_edge("draft", "compliance")
    g.add_edge("compliance", "route")
    g.add_edge("route", END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_pipeline(item_id: str, kind: str, payload: dict) -> dict:
    """Execute the full agent pipeline for one inbound item (sync; call in a thread)."""
    started = time.time()
    state: PipelineState = {
        "item_id": item_id,
        "kind": kind,
        "name": payload.get("name", ""),
        "email": payload.get("email", ""),
        "company": payload.get("company", ""),
        "subject": payload.get("subject", ""),
        "text": payload.get("message", "") or payload.get("body", ""),
    }
    try:
        final = get_graph().invoke(state)
        duration_ms = int((time.time() - started) * 1000)
        db.update_item(
            item_id,
            status=final.get("route", "auto_handled"),
            classification=final.get("intent"),
            score=final.get("score"),
            priority=final.get("priority"),
            summary=final.get("summary"),
            draft=final.get("draft"),
            risk_level=final.get("risk_level"),
            risk_notes=final.get("risk_notes"),
            engine=final.get("engine", "heuristic-fallback"),
            completed_at=time.time(),
            duration_ms=duration_ms,
        )
        # Real outbound: hot-lead/risk alert + auto-send on the originating channel
        if final.get("priority") == "hot" or final.get("risk_level") in ("medium", "high"):
            channels.alert_hot_lead(item_id, dict(final))
        if final.get("route") == "auto_handled":
            item = db.get_item(item_id)
            if item:
                channels.dispatch_reply(item)
        bus.emit(item_id, "Pipeline", f"Completed in {duration_ms} ms",
                 f"Final status: {final.get('route')}")
        return final
    except Exception as exc:  # never let a demo item hang in "processing"
        db.update_item(item_id, status="failed", completed_at=time.time())
        bus.emit(item_id, "Pipeline", "Pipeline error", str(exc)[:300])
        raise
    finally:
        bus.done(item_id)
