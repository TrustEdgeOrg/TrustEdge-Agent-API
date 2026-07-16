"""Fail-open client that upserts registered agents into TrustEdge backend."""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings
from app.models.schemas import RegisterRequest, RegisterResponse

logger = logging.getLogger(__name__)


def upsert_agent_to_trustedge(
    settings: Settings,
    req: RegisterRequest,
    response: RegisterResponse,
) -> None:
    """POST station details to TrustEdge. Never raises to the register path."""
    base = (settings.trustedge_backend_url or "").strip().rstrip("/")
    token = (settings.trustedge_ingest_token or "").strip()
    if not base:
        return

    payload: dict[str, Any] = {
        "agent_id": response.device_id,
        "hostname": req.hostname or None,
        "os": req.os or None,
        "os_version": req.os_version or None,
        "arch": req.arch or None,
        "agent_version": req.agent_version or None,
        "status": "registered",
    }
    # Drop nulls so TrustEdge upsert only overwrites provided fields.
    body = {k: v for k, v in payload.items() if v is not None}
    # agent_id is required
    body["agent_id"] = response.device_id

    import json

    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{base}/internal/agents/upsert"
    request = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=settings.trustedge_upsert_timeout_sec) as resp:
            if resp.status >= 400:
                logger.warning(
                    "TrustEdge agent upsert returned HTTP %s for agent_id=%s",
                    resp.status,
                    response.device_id,
                )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "TrustEdge agent upsert failed for agent_id=%s: %s",
            response.device_id,
            exc,
        )
