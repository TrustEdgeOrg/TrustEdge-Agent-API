"""Fail-open client that upserts registered agents into TrustEdge backend."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings
from app.models.schemas import RegisterRequest, RegisterResponse

logger = logging.getLogger(__name__)


def upsert_agent_fields(
    settings: Settings,
    agent_id: str,
    *,
    hostname: Optional[str] = None,
    os: Optional[str] = None,
    os_version: Optional[str] = None,
    arch: Optional[str] = None,
    agent_version: Optional[str] = None,
    status: str = "registered",
) -> None:
    """POST agent details to TrustEdge. Never raises to the caller."""
    base = (settings.trustedge_backend_url or "").strip().rstrip("/")
    token = (settings.trustedge_ingest_token or "").strip()
    if not base or not agent_id.strip():
        return

    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "hostname": hostname or None,
        "os": os or None,
        "os_version": os_version or None,
        "arch": arch or None,
        "agent_version": agent_version or None,
        "status": status or None,
    }
    # Drop nulls so TrustEdge upsert only overwrites provided fields.
    body = {k: v for k, v in payload.items() if v is not None}
    body["agent_id"] = agent_id

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
                    agent_id,
                )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "TrustEdge agent upsert failed for agent_id=%s: %s",
            agent_id,
            exc,
        )


def upsert_agent_to_trustedge(
    settings: Settings,
    req: RegisterRequest,
    response: RegisterResponse,
) -> None:
    """Upsert after Agent-API register (fail-open)."""
    upsert_agent_fields(
        settings,
        response.device_id,
        hostname=req.hostname or None,
        os=req.os or None,
        os_version=req.os_version or None,
        arch=req.arch or None,
        agent_version=req.agent_version or None,
        status="registered",
    )
