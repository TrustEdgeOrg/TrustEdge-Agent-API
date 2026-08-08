# <img src="assets/icons/api.svg" width="28" height="28" align="absmiddle" alt="" /> TrustEdge Agent API

Ingest API for the [TrustEdge](https://github.com/TrustEdgeOrg/TrustEdge) security observability platform. Agents POST endpoint telemetry; the API can optionally publish to Kafka for detection.

Pairs with [TrustEdge-Agent](https://github.com/TrustEdgeOrg/TrustEdge-Agent).

> Local base URL example: `http://127.0.0.1:8080`

---

## <img src="assets/icons/layout.svg" width="22" height="22" align="absmiddle" alt="" /> Event envelope

All telemetry uses one envelope:

```json
{
  "event_id": "evt_...",
  "device_id": "dev_...",
  "type": "client_details | network_summary | network_connection | action_summary | process_start | process_exit | file_open | driver_load | service_install | registry_persistence | known_ai_app",
  "ts": "2026-07-03T21:00:00Z",
  "payload": {}
}
```

---

## <img src="assets/icons/upload.svg" width="22" height="22" align="absmiddle" alt="" /> Endpoints

### <img src="assets/icons/flow.svg" width="18" height="18" align="absmiddle" alt="" /> `GET /healthz`

Health check.

**Response:** `200 OK`

```json
{ "status": "ok" }
```

### <img src="assets/icons/lock.svg" width="18" height="18" align="absmiddle" alt="" /> `POST /v1/register`

Register a client (device). When `TRUSTEDGE_AGENT_ENROLL_TOKEN` is set (required in production), send `Authorization: Bearer <enroll_token>`.

**Request:**

```json
{
  "device_id": "optional-existing-id",
  "hostname": "endpoint-01",
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

### <img src="assets/icons/collection.svg" width="18" height="18" align="absmiddle" alt="" /> `POST /v1/events`

Ingest one or more events. Requires `Authorization: Bearer <device_token>`.

#### Single event

Send a single `Event` object:

```json
{
  "event_id": "evt_...",
  "device_id": "dev_...",
  "type": "client_details",
  "ts": "2026-07-03T21:00:00Z",
  "payload": { "hostname": "endpoint-01", "status": "online" }
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

The server accepts either format. Maximum **100 events** per request (`MAX_EVENTS_PER_BATCH`).

**Response:** `202 Accepted`

```json
{
  "status": "accepted",
  "accepted": 2
}
```

#### <img src="assets/icons/compress.svg" width="16" height="16" align="absmiddle" alt="" /> Compression

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

### <img src="assets/icons/agent.svg" width="18" height="18" align="absmiddle" alt="" /> `GET /v1/clients/{id}`

Return latest client details and recent events (for demos / debugging). **No auth** — do not expose publicly without a reverse proxy or network controls.

**Response:** `200 OK`

```json
{
  "device_id": "dev_...",
  "last_details": { "hostname": "endpoint-01", "status": "online" },
  "last_seen_at": "2026-07-03T21:00:00Z",
  "recent_events": [ ... ]
}
```

---

## <img src="assets/icons/flow.svg" width="22" height="22" align="absmiddle" alt="" /> Side effects on ingest

After a successful `POST /v1/events` (and similarly on register where noted):

| Path | When | Behavior |
|------|------|----------|
| Disk | `TRUSTEDGE_AGENT_PERSIST_FILES` not `0` | Append to `events.jsonl`; update `devices.json` |
| Kafka | `KAFKA_BROKERS` set | Publish each accepted event to `KAFKA_TOPIC` |
| Redis twin | `REDIS_URL` set | Fail-open update of `twin:devices`, `twin:device:{id}:latest`, events ZSET (cap 200) |
| TrustEdge registry | `TRUSTEDGE_BACKEND_URL` set | Fail-open background `POST /internal/agents/upsert` (register + ingest) |

Twin “latest” folds `client_details`, `network_summary`, `action_summary`, and `known_ai_apps`. Other event types still land in the events ZSET.

---

## <img src="assets/icons/collection.svg" width="22" height="22" align="absmiddle" alt="" /> Event types

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

Coarse network posture (counts and top ports — not a full connection dump).

| Field | Description |
|-------|-------------|
| `public_ip` | Public IPv4 |
| `network_type` | `wifi`, `ethernet`, `unknown` |
| `listening_count` | Listening sockets |
| `established_count` | Established TCP |
| `top_remote_ports` | `[{port, count}, …]` |
| `foreground_app_connections` | Optional app-linked count |

### `network_connection`

Incremental ESTABLISHED TCP sample from the agent (poll-based; not a full table dump). Accepted and streamed/persisted like other events; not folded into Redis twin “latest” fields (still appears in the twin events ZSET).

| Field | Description |
|-------|-------------|
| `pid` | Owning process ID |
| `comm` | Short process name when available |
| `protocol` | Typically `tcp` |
| `local_addr` / `local_port` | Local endpoint |
| `remote_addr` / `remote_ip` / `remote_port` | Remote endpoint |
| `direction` | Direction hint when present |
| `remote_hostname` / `domain` | Optional reverse-DNS enrichment |

Disable on the agent with `TRUSTEDGE_AGENT_CONNECTION_INTERVAL=0`.

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

EDR-lite process visibility.

| Field | Description |
|-------|-------------|
| `pid` | Process ID |
| `ppid` | Parent process ID |
| `user` | Owning user |
| `comm` | Short process name |
| `executable` | Binary path or name |
| `cmdline` | Command line (truncated; optional) |

### `file_open`

Accepted by the API for forward compatibility. The current TrustEdge Agent does not emit this type by default.

### `driver_load`

Newly observed loaded driver (Windows) or kext (macOS).

| Field | Description |
|-------|-------------|
| `name` | Driver / kext identifier |
| `display_name` | Human-readable name when available |
| `path` | Image / plist path when available |
| `state` / `status` | Runtime state |
| `service_type` | e.g. driver class or `kext` |

### `service_install`

Newly observed Windows service or macOS LaunchDaemon.

| Field | Description |
|-------|-------------|
| `name` | Service name / launchd label |
| `display_name` | Display name when available |
| `path` | Binary or plist path |
| `start_mode` | Start type / LaunchDaemon |
| `account` | Run-as account / hive scope when available |

### `known_ai_app`

Known AI tools inventory upsert or removal (folded into Redis twin `known_ai_apps`). Covers GUI apps, CLI agents, local model runtimes, and IDE extensions matched from a verified catalog.

| Field | Description |
|-------|-------------|
| `id` | Stable instance id (`product_id:path_key`) |
| `product_id` | Catalog id (`cursor`, `claude`, `ollama`, `cline`, …) |
| `product_name` | Display name |
| `vendor` | Vendor name |
| `category` | e.g. `code_editor`, `chat_client`, `cli_agent`, `local_model_runtime`, `ai_ide_extension`, `agentic_ide_extension` |
| `confidence` | Identification confidence |
| `confidence_reason` | Optional human-readable match explanation |
| `installed` / `running` | Presence flags |
| `path` / `version` / `bundle_id` | Install metadata |
| `matched_evidence` / `failed_evidence` | Evidence keys from catalog matching |
| `invocation_path` / `resolved_path` / `package_manager` / `package_identifier` | CLI / package identity when applicable |
| `serving` / `exposure` / `listeners` / `models_available` / `model_format` / `runtime_version` / `local_clients` | Local model runtime fields when applicable |
| `extension_id` / `host_ide_product_id` / `host_ide_path` / `profile` | IDE extension fields when applicable |
| `enabled` / `active` | Extension enabled/active when known (`active` often unknown for shared hosts) |
| `mcp_configured` / `local_model_product_id` | Extension capability / correlation hints |
| `removed` | When true, delete this `id` from twin inventory |

### `registry_persistence`

New or changed persistence artifact: Windows Run/RunOnce or macOS LaunchAgent.

| Field | Description |
|-------|-------------|
| `hive` | Registry hive or macOS scope (`user` / `system`) |
| `key_path` | Registry key or LaunchAgents directory |
| `value_name` | Value name / launchd label |
| `value` | Command / program arguments |
| `path` | Optional plist path (macOS) |

---

## <img src="assets/icons/lock.svg" width="22" height="22" align="absmiddle" alt="" /> Production

When `TRUSTEDGE_AGENT_PRODUCTION=1`:

- API refuses to start without `TRUSTEDGE_AGENT_ENROLL_TOKEN`.
- Agents refuse to start without `TRUSTEDGE_AGENT_ENROLL_TOKEN` and an `https://` API URL.
- Device tokens are stored in the OS keyring, not `state.json`.

See [Configuration](configuration.md) for all environment variables.

---

## <img src="assets/icons/privacy.svg" width="22" height="22" align="absmiddle" alt="" /> Privacy

TrustEdge Agent does **not** collect window titles, URLs, keystrokes, screenshots, or raw SSIDs. Connection samples (`network_connection`) are incremental and capped — not full table dumps — and can be disabled with `TRUSTEDGE_AGENT_CONNECTION_INTERVAL=0`.

Process monitoring includes metadata and a truncated command line — not file contents. Disable processes with `TRUSTEDGE_AGENT_PROCESS_INTERVAL=0`.

---

## <img src="assets/icons/config.svg" width="22" height="22" align="absmiddle" alt="" /> Related docs

| | Doc | Purpose |
|---|-----|---------|
| <img src="assets/icons/config.svg" width="18" height="18" align="absmiddle" alt="" /> | [Configuration](configuration.md) | Environment variables |
| <img src="assets/icons/platforms.svg" width="18" height="18" align="absmiddle" alt="" /> | [AWS deploy](../aws/README.md) | ECR build and EC2 deploy |
| <img src="assets/icons/agent.svg" width="18" height="18" align="absmiddle" alt="" /> | [TrustEdge-Agent](https://github.com/TrustEdgeOrg/TrustEdge-Agent) | Endpoint agent |
| <img src="assets/icons/architecture.svg" width="18" height="18" align="absmiddle" alt="" /> | [TrustEdge deploy](https://github.com/TrustEdgeOrg/TrustEdge/blob/main/docs/DEPLOY.md) | Production AWS layout |
