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


def test_rotate_and_revoke_device(api_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("TRUSTEDGE_AGENT_ENROLL_TOKEN", "enroll-secret")
    # Recreate app so settings pick up enroll token.
    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        reg = client.post(
            "/v1/register",
            headers={"Authorization": "Bearer enroll-secret"},
            json={"hostname": "rotate-box"},
        )
        assert reg.status_code == 200
        token = reg.json()["device_token"]
        device_id = reg.json()["device_id"]

        rotated = client.post(
            "/v1/devices/rotate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rotated.status_code == 200
        new_token = rotated.json()["device_token"]
        assert new_token != token

        old = client.post(
            "/v1/events",
            headers={"Authorization": f"Bearer {token}"},
            json={"type": "client_details", "payload": {"hostname": "rotate-box"}},
        )
        assert old.status_code == 401

        ok = client.post(
            "/v1/events",
            headers={"Authorization": f"Bearer {new_token}"},
            json={"type": "client_details", "payload": {"hostname": "rotate-box"}},
        )
        assert ok.status_code == 202

        revoked = client.post(
            f"/v1/devices/{device_id}/revoke",
            headers={"Authorization": "Bearer enroll-secret"},
        )
        assert revoked.status_code == 204

        after = client.post(
            "/v1/events",
            headers={"Authorization": f"Bearer {new_token}"},
            json={"type": "client_details", "payload": {"hostname": "rotate-box"}},
        )
        assert after.status_code == 401
    get_settings.cache_clear()
