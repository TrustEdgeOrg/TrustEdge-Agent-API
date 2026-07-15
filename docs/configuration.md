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

### <img src="assets/icons/queue.svg" width="18" height="18" align="absmiddle" alt="" /> Persistence

By default the API keeps state in memory and writes `devices.json` / `events.jsonl` under `TRUSTEDGE_AGENT_DATA_DIR`. Set `TRUSTEDGE_AGENT_PERSIST_FILES=0` for ephemeral in-memory-only mode.

### <img src="assets/icons/lock.svg" width="18" height="18" align="absmiddle" alt="" /> Production API checklist

```bash
export TRUSTEDGE_AGENT_PRODUCTION=1
export TRUSTEDGE_AGENT_ENROLL_TOKEN=<generate-secure-token>
export KAFKA_BROKERS=127.0.0.1:9092
export KAFKA_TOPIC=trustedge.agent.events
```

> Do not commit real enroll tokens or broker credentials. Prefer placeholders in docs and `.env.example`.

---

## <img src="assets/icons/platforms.svg" width="22" height="22" align="absmiddle" alt="" /> Docker / deploy

The TrustEdge `docker-compose.yml` profile `agent` can run `trustedge-agent-api` from ECR. Environment is injected by compose — see [AWS deploy](../aws/README.md).

Typical production env (compose or host config):

- `TRUSTEDGE_AGENT_PRODUCTION=1`
- `TRUSTEDGE_AGENT_ENROLL_TOKEN` — from your secrets store / host token file
- `KAFKA_BROKERS` — stream broker on the private network

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
