# TrustEdge Agent API

Ingest API for the [TrustEdge](https://github.com/TrustEdgeOrg/TrustEdge) security observability platform. Agents POST endpoint telemetry; production mode mirrors to Redis and publishes to Kafka for detection.

Base URL example: `http://127.0.0.1:8080`

## Event envelope

All telemetry uses one envelope:

```json
{
  "event_id": "evt_...",
  "device_id": "dev_...",
  "type": "client_details | network_summary | action_summary | process_start | process_exit",
  "ts": "2026-07-03T21:00:00Z",
  "payload": {}
}
```

## Endpoints

### `GET /healthz`

Health check.

**Response:** `200 OK`

```json
{ "status": "ok" }
```

### `POST /v1/register`

Register a client (device). When `TRUSTEDGE_AGENT_ENROLL_TOKEN` is set (required in production), send `Authorization: Bearer <enroll_token>`.

**Request:**

```json
{
  "device_id": "optional-existing-id",
  "hostname": "elad-mbp",
  "os": "darwin",
  "os_version": "15.5",
  "arch": "arm64",
  "agent_version": "0.1.0"
}
```

**Response:** `200 OK`

```json
{
  "device_id": "dev_...",
  "device_token": "tok_..."
}
```

### `POST /v1/events`

Ingest one or more events. Requires `Authorization: Bearer <device_token>`.

#### Single event

Send a single `Event` object:

```json
{
  "event_id": "evt_...",
  "device_id": "dev_...",
  "type": "client_details",
  "ts": "2026-07-03T21:00:00Z",
  "payload": { "hostname": "elad-mbp", "status": "online" }
}
```

#### Batch

Send an `EventBatch` wrapper (used by the agent for multi-event flushes):

```json
{
  "events": [
    { "type": "process_start", "payload": { "pid": 1234, "comm": "curl" } },
    { "type": "process_exit", "payload": { "pid": 1234, "comm": "curl" } }
  ]
}
```

The server accepts either format. Maximum **100 events** per request (`MaxEventsPerBatch`).

**Response:** `202 Accepted`

```json
{
  "status": "accepted",
  "accepted": 2
}
```

#### Compression

The agent may send zstd-compressed bodies:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `Content-Encoding` | `zstd` |

The API decompresses when `Content-Encoding: zstd` is present. Uncompressed JSON remains accepted for backward compatibility.

Compression is applied only when the zstd output is smaller than the original JSON. Typical batches compress well; very small payloads may stay uncompressed.

#### Errors

| Status | Condition |
|--------|-----------|
| `400` | Invalid JSON, unknown event type, empty batch, batch too large |
| `401` | Missing or invalid device token |
| `403` | Event `device_id` does not match token |
| `500` | Internal store error |

### `GET /v1/clients/{id}`

Return latest client details and recent events (for demos / debugging).

**Response:** `200 OK`

```json
{
  "device_id": "dev_...",
  "last_details": { "hostname": "...", "status": "online" },
  "last_seen_at": "2026-07-03T21:00:00Z",
  "recent_events": [ ... ]
}
```

## Event types

### `client_details`

Identity + presence heartbeat.

| Field | Description |
|-------|-------------|
| `hostname` | Machine name |
| `os` | `darwin`, `linux`, `windows` |
| `os_version` | OS version string |
| `arch` | `arm64`, `amd64` |
| `agent_version` | Agent version |
| `timezone` | Local timezone abbreviation |
| `status` | `online` |
| `uptime_sec` | Agent uptime |

### `network_summary`

Coarse network posture (no raw connection tables).

| Field | Description |
|-------|-------------|
| `public_ip` | Public IPv4 |
| `network_type` | `wifi`, `ethernet`, `unknown` |
| `listening_count` | Listening sockets |
| `established_count` | Established TCP |
| `top_remote_ports` | `[{port, count}, …]` |
| `foreground_app_connections` | Optional app-linked count |

### `action_summary`

Short-window behavior (no daily rollup in v1).

| Field | Description |
|-------|-------------|
| `window_start` / `window_end` | Window bounds (RFC3339) |
| `focus` | App focus entries |
| `presence` | `active` or `idle` |
| `idle_sec` | Seconds since last input |
| `app_switches` | Focus changes in window |

### `process_start` / `process_exit`

EDR-lite process visibility (metadata only).

| Field | Description |
|-------|-------------|
| `pid` | Process ID |
| `ppid` | Parent process ID |
| `user` | Owning user |
| `comm` | Short process name |
| `executable` | Binary path or comm |

## Production

When `TRUSTEDGE_AGENT_PRODUCTION=1`:

- API refuses to start without `TRUSTEDGE_AGENT_ENROLL_TOKEN` and `REDIS_URL`.
- Agents refuse to start without `TRUSTEDGE_AGENT_ENROLL_TOKEN` and an `https://` API URL.
- Device tokens are stored in the OS keyring, not `state.json`.

See [Configuration](configuration.md) for all environment variables.

## Privacy

TrustEdge Agent does **not** collect window titles, URLs, keystrokes, screenshots, raw SSIDs, or full remote IP connection lists.

Process monitoring collects metadata only — not command lines or file contents.
