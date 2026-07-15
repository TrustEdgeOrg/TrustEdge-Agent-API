from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Event(BaseModel):
    event_id: str = ""
    device_id: str = ""
    type: str = ""
    ts: Optional[datetime] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    events: List[Event] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    device_id: str = ""
    hostname: str = ""
    os: str = ""
    os_version: str = ""
    arch: str = ""
    agent_version: str = ""


class RegisterResponse(BaseModel):
    device_id: str
    device_token: str


class ClientView(BaseModel):
    device_id: str
    last_details: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[datetime] = None
    recent_events: List[Event] = Field(default_factory=list)
