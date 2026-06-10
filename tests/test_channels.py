"""Tests for channel integrations: Telegram webhook, intake auth, config, dispatch."""
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import config, db


@pytest.fixture()
def client(tmp_path):
    config.GROQ_API_KEY = None
    config.INTAKE_API_KEY = None
    config.TELEGRAM_BOT_TOKEN = None
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


def test_config_endpoint(client):
    c = client.get("/api/config").json()
    assert c["engine"] == "heuristic-fallback"
    assert c["telegram"]["enabled"] is False
    assert c["email_out"] is False


def test_pages_served(client):
    for path in ("/", "/contact", "/integrations"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "<html" in r.text.lower()
    assert client.get("/static/logo.svg").status_code == 200


def test_telegram_webhook_creates_item(client):
    update = {"update_id": 1, "message": {
        "chat": {"id": 12345}, "text": "We need a demo urgently, budget approved!",
        "from": {"first_name": "Test", "last_name": "User", "username": "testuser"}}}
    with patch("app.channels.send_telegram", return_value=True) as mock_send:
        r = client.post("/api/telegram/webhook", json=update)
        assert r.status_code == 200
        item_id = r.json()["item_id"]
        assert item_id
        item = _wait_done(client, item_id)
    assert item["kind"] == "telegram"
    assert item["payload"]["chat_id"] == 12345
    assert item["priority"] == "hot"
    mock_send.assert_called()  # ack message sent


def test_telegram_start_command_ignored(client):
    update = {"update_id": 2, "message": {
        "chat": {"id": 99}, "text": "/start", "from": {"first_name": "New"}}}
    with patch("app.channels.send_telegram", return_value=True):
        r = client.post("/api/telegram/webhook", json=update)
    assert r.json()["item_id"] is None


def test_approve_dispatches_telegram_reply(client):
    update = {"update_id": 3, "message": {
        "chat": {"id": 777}, "text": "Enterprise contract, budget ready, pricing needed immediately, urgent",
        "from": {"first_name": "Buyer"}}}
    with patch("app.channels.send_telegram", return_value=True):
        item_id = client.post("/api/telegram/webhook", json=update).json()["item_id"]
        item = _wait_done(client, item_id)
    assert item["status"] == "pending_approval"
    with patch("app.channels.send_telegram", return_value=True) as mock_send:
        r = client.post(f"/api/items/{item_id}/approve", json={"note": "ship it"})
        assert r.status_code == 200
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == 777      # chat_id
        assert item["draft"] in mock_send.call_args[0][1]


def test_intake_api_key_enforced(client):
    config.INTAKE_API_KEY = "secret123"
    try:
        body = {"name": "X", "email": "x@y.com", "message": "hello there friend"}
        # machine caller without key -> 401
        assert client.post("/api/leads", json=body).status_code == 401
        # wrong key -> 401
        assert client.post("/api/leads", json=body,
                           headers={"X-API-Key": "wrong"}).status_code == 401
        # correct key -> 202
        assert client.post("/api/leads", json=body,
                           headers={"X-API-Key": "secret123"}).status_code == 202
        # browser same-origin (dashboard/contact page) stays open
        assert client.post("/api/leads", json=body,
                           headers={"Sec-Fetch-Site": "same-origin"}).status_code == 202
    finally:
        config.INTAKE_API_KEY = None


def test_email_dispatch_attempted_on_auto_handled(client):
    with patch("app.channels.send_email", return_value=(True, "id x")) as mock_email:
        r = client.post("/api/emails", json={
            "name": "Sam", "email": "sam@example.com", "subject": "hi",
            "body": "Just curious about your features."})
        item = _wait_done(client, r.json()["item_id"])
    assert item["status"] == "auto_handled"
    mock_email.assert_called_once()
    assert mock_email.call_args[0][0] == "sam@example.com"
