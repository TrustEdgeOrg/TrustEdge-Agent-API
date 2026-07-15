from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def api_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TRUSTEDGE_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TRUSTEDGE_AGENT_PRODUCTION", "0")
    with TestClient(create_app()) as client:
        yield client


def test_healthz(api_client: TestClient) -> None:
    resp = api_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_and_events_flow(api_client: TestClient) -> None:
    reg = api_client.post("/v1/register", json={"hostname": "mbp", "os": "darwin"})
    assert reg.status_code == 200
    token = reg.json()["device_token"]
    device_id = reg.json()["device_id"]

    events = api_client.post(
        "/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"events": [{"type": "client_details", "payload": {"hostname": "mbp", "status": "online"}}]},
    )
    assert events.status_code == 202
    assert events.json()["accepted"] == 1

    client_view = api_client.get(f"/v1/clients/{device_id}")
    assert client_view.status_code == 200
    assert client_view.json()["device_id"] == device_id
