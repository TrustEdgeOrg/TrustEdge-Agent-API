from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.clients.trustedge_backend import upsert_agent_fields, upsert_agent_to_trustedge
from app.config import Settings
from app.models.schemas import RegisterRequest, RegisterResponse


def _settings(**env: str) -> Settings:
    payload = {
        "TRUSTEDGE_BACKEND_URL": env.get("TRUSTEDGE_BACKEND_URL", ""),
        "TRUSTEDGE_INGEST_TOKEN": env.get("TRUSTEDGE_INGEST_TOKEN", ""),
        "TRUSTEDGE_UPSERT_TIMEOUT_SEC": env.get("TRUSTEDGE_UPSERT_TIMEOUT_SEC", "5"),
    }
    return Settings.model_validate(payload)


def test_upsert_skipped_when_backend_url_empty() -> None:
    settings = _settings()
    with patch("app.clients.trustedge_backend.urlopen") as urlopen:
        upsert_agent_to_trustedge(
            settings,
            RegisterRequest(hostname="x"),
            RegisterResponse(device_id="dev_1", device_token="tok"),
        )
        urlopen.assert_not_called()


def test_upsert_posts_payload() -> None:
    settings = _settings(
        TRUSTEDGE_BACKEND_URL="http://backend:8000",
        TRUSTEDGE_INGEST_TOKEN="secret",
        TRUSTEDGE_UPSERT_TIMEOUT_SEC="2",
    )
    assert settings.trustedge_backend_url == "http://backend:8000"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("app.clients.trustedge_backend.urlopen", return_value=mock_resp) as urlopen:
        upsert_agent_to_trustedge(
            settings,
            RegisterRequest(hostname="mbp", os="darwin", agent_version="1.0"),
            RegisterResponse(device_id="dev_abc", device_token="tok"),
        )
        urlopen.assert_called_once()
        req = urlopen.call_args[0][0]
        assert req.full_url == "http://backend:8000/internal/agents/upsert"
        auth = req.headers.get("Authorization") or req.get_header("Authorization")
        assert auth == "Bearer secret"
        body = req.data.decode("utf-8")
        assert "dev_abc" in body
        assert "mbp" in body


def test_upsert_fields_from_events_path() -> None:
    settings = _settings(TRUSTEDGE_BACKEND_URL="http://backend:8000", TRUSTEDGE_INGEST_TOKEN="t")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("app.clients.trustedge_backend.urlopen", return_value=mock_resp) as urlopen:
        upsert_agent_fields(
            settings,
            "dev_xyz",
            hostname="host1",
            os="linux",
            status="active",
        )
        urlopen.assert_called_once()
        body = urlopen.call_args[0][0].data.decode("utf-8")
        assert "dev_xyz" in body
        assert "active" in body


def test_upsert_fail_open_on_network_error() -> None:
    settings = _settings(TRUSTEDGE_BACKEND_URL="http://backend:8000")
    with patch("app.clients.trustedge_backend.urlopen", side_effect=OSError("down")):
        upsert_agent_to_trustedge(
            settings,
            RegisterRequest(hostname="x"),
            RegisterResponse(device_id="dev_1", device_token="tok"),
        )
