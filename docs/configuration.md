# <img src="assets/icons/config.svg" width="28" height="28" align="absmiddle" alt="" /> Configuration

All settings are environment variables. Copy [.env.example](../.env.example) as a starting point.

---

## <img src="assets/icons/api.svg" width="22" height="22" align="absmiddle" alt="" /> API (`trustedge-agent-api`)

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUSTEDGE_AGENT_LISTEN` | `:8080` | HTTP listen address |
| `TRUSTEDGE_AGENT_ENROLL_TOKEN` | _(empty)_ | Required for registration when set; required in production |
| `TRUSTEDGE_AGENT_PRODUCTION` | `0` | `1` requires enroll token |
| `TRUSTEDGE_AGENT_DATA_DIR` | `data` | Directory for `devices.json` / `events.jsonl` |
| `TRUSTEDGE_AGENT_PERSIST_FILES` | `1` | `1`/`0` to enable or disable disk writes |
| `KAFKA_BROKERS` | _(empty)_ | Comma-separated brokers; unset disables Kafka publish |
| `KAFKA_TOPIC` | `trustedge.agent.events` | Kafka topic for ingested events |
| `REDIS_URL` | _(empty)_ | Live twin Redis only; unset disables twin writes (fail-open) |
| `TRUSTEDGE_BACKEND_URL` | _(empty)_ | TrustEdge FastAPI base for agents upsert; unset skips |
| `TRUSTEDGE_INGEST_TOKEN` | _(empty)_ | Bearer for `/internal/agents/upsert` (match TrustEdge) |
| `TRUSTEDGE_UPSERT_TIMEOUT_SEC` | `5` | Upsert HTTP timeout |
| `TRUSTEDGE_DEVICE_TOKEN_PEPPER` | _(empty)_ | Optional HMAC pepper for device-token digests at rest |
| `TRUSTEDGE_DEVICE_TOKEN_TTL_SEC` | `0` | Device token lifetime in seconds; `0` disables expiry |
| `TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL` | _(empty)_ | **Agent-API-owned** Postgres for `token_hash → device_id` (multi-replica). Empty = local/memory map. Do **not** point at the TrustEdge control-plane database. |
| `TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL` | _(empty)_ | Optional auth-cache Redis (advanced). Empty = **Postgres-only** lookups (recommended default). |
| `TRUSTEDGE_AGENT_DEVICE_CREDS_CACHE_TTL_SEC` | `300` | Auth cache TTL (seconds) when Redis URL is set; capped by token expiry |

### <img src="assets/icons/lock.svg" width="18" height="18" align="absmiddle" alt="" /> Device tokens

Device upload credentials are **opaque** (`tok_…`), not JWTs. The API stores only a **hash** in `devices.json` (legacy plaintext is migrated on load).

| Behavior | Detail |
|----------|--------|
| Register / re-register | Always **rotates** the device token and returns the new plaintext once |
| Ingest auth | Bearer device token → hash lookup → device id |
| Rotate | `POST /v1/devices/rotate` with current device bearer |
| Revoke | `POST /v1/devices/{device_id}/revoke` with enroll bearer (when configured) |
| TTL | Optional `TRUSTEDGE_DEVICE_TOKEN_TTL_SEC`; expired tokens fail ingest with 401 |
| Shared store | Dedicated Postgres via `TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL` so all API replicas share the same `token_hash → device_id` map |
| Auth cache | Optional Redis (`TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL`) — unused by default; Postgres is enough at typical load |
| Live twin | Separate Redis (`REDIS_URL`) — presence / latest / recent events. Fail-open. |

Table (when Postgres is enabled): `agent_device_credentials`  
Columns: `device_id`, `token_hash`, `token_expires_at`, `revoked_at`, `last_seen_at`, …

Postgres is the durable source of truth for device credentials. Auth never fail-opens: missing credentials still return 401.

**Database ownership:** use a database dedicated to Agent-API (dev compose: `postgres-agent-api` / `trustedge_agent_api`). TrustEdge control-plane Postgres stores agent **metadata only** — never device tokens — and must not share a connection string with device creds.

**Cutover from a shared control-plane table:** if `agent_device_credentials` already exists on the control-plane DB, copy those rows into the Agent-API database (`pg_dump`/`COPY`) before switching `TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL`.

Optional Redis auth-cache keys (only when `TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL` is set):
- `device_creds:token:{token_hash}` → `device_id`
- `device_creds:device:{device_id}:hash` → current `token_hash` (for invalidation)

### <img src="assets/icons/queue.svg" width="18" height="18" align="absmiddle" alt="" /> Persistence

By default the API keeps state in memory and writes `devices.json` / `events.jsonl` under `TRUSTEDGE_AGENT_DATA_DIR`. Set `TRUSTEDGE_AGENT_PERSIST_FILES=0` for ephemeral in-memory-only mode.

### <img src="assets/icons/flow.svg" width="18" height="18" align="absmiddle" alt="" /> Streaming & twin

| Feature | Enable with |
|---------|-------------|
| Kafka publish | `KAFKA_BROKERS` |
| Redis live twin | `REDIS_URL` |
| TrustEdge agents registry | `TRUSTEDGE_BACKEND_URL` (+ optional `TRUSTEDGE_INGEST_TOKEN`) |

All three are fail-open: ingest still returns `202` if publish, twin, or upsert fails.

### <img src="assets/icons/lock.svg" width="18" height="18" align="absmiddle" alt="" /> Production API checklist

```bash
export TRUSTEDGE_AGENT_PRODUCTION=1
export TRUSTEDGE_AGENT_ENROLL_TOKEN=<generate-secure-token>
# Optional hardening:
# export TRUSTEDGE_DEVICE_TOKEN_PEPPER=<random-pepper>
# export TRUSTEDGE_DEVICE_TOKEN_TTL_SEC=2592000
export KAFKA_BROKERS=127.0.0.1:9092
export KAFKA_TOPIC=trustedge.agent.events
export REDIS_URL=redis://redis:6379/0
# Dedicated Agent-API credentials DB (not control-plane RDS):
export TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL=postgresql://user:pass@host:5432/trustedge_agent_api
# Optional at high QPS / many replicas only:
# export TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL=redis://…:6379/0
export TRUSTEDGE_BACKEND_URL=http://backend:8000
export TRUSTEDGE_INGEST_TOKEN=<same-as-trustedge-backend>
```

> Do not commit real enroll tokens, ingest tokens, or broker credentials. Prefer placeholders in docs and `.env.example`.

---

## <img src="assets/icons/platforms.svg" width="22" height="22" align="absmiddle" alt="" /> Docker / deploy

The TrustEdge `docker-compose.yml` profile `agent` can run `trustedge-agent-api` from ECR. Environment is injected by compose — see [AWS deploy](../aws/README.md) and [TrustEdge DEPLOY](https://github.com/TrustEdgeOrg/TrustEdge/blob/main/docs/DEPLOY.md).

Typical production env (compose or host config):

- `TRUSTEDGE_AGENT_PRODUCTION=1`
- `TRUSTEDGE_AGENT_ENROLL_TOKEN` — from your secrets store / host token file
- `KAFKA_BROKERS` — stream broker on the private network
- `REDIS_URL` — twin Redis (`redis` service)
- `TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL` — **dedicated** Postgres database for device credentials (separate from control-plane RDS)
- `TRUSTEDGE_BACKEND_URL` / `TRUSTEDGE_INGEST_TOKEN` — agents registry upsert

---

## <img src="assets/icons/concurrency.svg" width="22" height="22" align="absmiddle" alt="" /> CI

API deploy CI (`.github/workflows/deploy-api.yml`) runs tests, builds the Docker image, pushes to ECR, and deploys on push to `develop` or `main`.

---

## <img src="assets/icons/layout.svg" width="22" height="22" align="absmiddle" alt="" /> Related docs

| | Doc | Purpose |
|---|-----|---------|
| <img src="assets/icons/api.svg" width="18" height="18" align="absmiddle" alt="" /> | [API reference](api.md) | HTTP endpoints and payloads |
| <img src="assets/icons/platforms.svg" width="18" height="18" align="absmiddle" alt="" /> | [AWS deploy](../aws/README.md) | ECR and EC2 setup |
| <img src="assets/icons/agent.svg" width="18" height="18" align="absmiddle" alt="" /> | [TrustEdge-Agent](https://github.com/TrustEdgeOrg/TrustEdge-Agent) | Endpoint agent |
