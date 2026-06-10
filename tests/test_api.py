"""End-to-end API tests. No GROQ_API_KEY needed — the heuristic fallback engine runs."""
import time

import pytest
from fastapi.testclient import TestClient

from app import config, db


@pytest.fixture()
def client(tmp_path):
    config.GROQ_API_KEY = None  # force heuristic engine in CI
    db.reset_for_tests(str(tmp_path / "test.db"))
    from app.main import app
    with TestClient(app) as c:
        yield c
    db.reset_for_tests()


def _wait_done(client, item_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = client.get(f"/api/items/{item_id}").json()
        if item["status"] != "processing":
            return item
        time.sleep(0.1)
    raise AssertionError("pipeline did not finish in time")


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_seed_data_loaded(client):
    items = client.get("/api/items").json()
    assert len(items) >= 3


def test_hot_lead_goes_to_approval_queue(client):
    r = client.post("/api/leads", json={
        "name": "Jane Buyer", "email": "jane@bigco.com", "company": "BigCo",
        "message": "Urgent: we have budget approved and need a demo ASAP before our deadline."})
    assert r.status_code == 202
    item = _wait_done(client, r.json()["item_id"])
    assert item["priority"] == "hot"
    assert item["status"] == "pending_approval"
    assert item["draft"]
    agents = {t["agent"] for t in item["trace"]}
    assert {"Triage Agent", "Scoring Agent", "Drafting Agent",
            "Compliance Agent", "Routing Agent"} <= agents


def test_cold_email_is_auto_handled(client):
    r = client.post("/api/emails", json={
        "name": "Sam", "email": "sam@x.com", "subject": "hello",
        "body": "Just saying hi, love your blog posts."})
    item = _wait_done(client, r.json()["item_id"])
    assert item["status"] == "auto_handled"


def test_risky_email_flags_compliance(client):
    r = client.post("/api/emails", json={
        "name": "Angry Customer", "email": "ac@corp.com", "subject": "Refund or lawsuit",
        "body": "I want to cancel and get a refund or my lawyer will file a lawsuit."})
    item = _wait_done(client, r.json()["item_id"])
    assert item["risk_level"] == "high"
    assert item["status"] == "pending_approval"


def test_approve_flow(client):
    r = client.post("/api/leads", json={
        "name": "Hot Lead", "email": "h@l.com", "company": "Enterprise Inc",
        "message": "Enterprise contract, budget ready, need pricing immediately, urgent."})
    item = _wait_done(client, r.json()["item_id"])
    assert item["status"] == "pending_approval"
    ok = client.post(f"/api/items/{item['id']}/approve", json={"note": "LGTM"})
    assert ok.status_code == 200
    assert client.get(f"/api/items/{item['id']}").json()["status"] == "approved"
    # double-approve conflicts
    assert client.post(f"/api/items/{item['id']}/approve").status_code == 409


def test_validation_rejects_empty_message(client):
    assert client.post("/api/leads", json={"message": ""}).status_code == 422


def test_metrics(client):
    m = client.get("/api/metrics").json()
    assert m["total_items"] >= 3
    assert "pending_approvals" in m
