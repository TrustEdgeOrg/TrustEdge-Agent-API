# Configuration

All settings are environment variables. Copy [.env.example](../.env.example) as a starting point.

## API (`trustedge-agent-api`)

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUSTEDGE_AGENT_LISTEN` | `:8080` | HTTP listen address |
| `TRUSTEDGE_AGENT_ENROLL_TOKEN` | _(empty)_ | Required for registration when set; required in production |
| `TRUSTEDGE_AGENT_PRODUCTION` | `0` | `1` requires enroll token |
| `TRUSTEDGE_AGENT_DATA_DIR` | `data` | Directory for `devices.json` / `events.jsonl` |
| `TRUSTEDGE_AGENT_PERSIST_FILES` | `1` | `1`/`0` to enable or disable disk writes |
| `KAFKA_BROKERS` | _(empty)_ | Comma-separated brokers; unset disables Kafka publish |
| `KAFKA_TOPIC` | `trustedge.agent.events` | Kafka topic for ingested events |

### Persistence

By default the API keeps state in memory and writes `devices.json` / `events.jsonl` under `TRUSTEDGE_AGENT_DATA_DIR`. Set `TRUSTEDGE_AGENT_PERSIST_FILES=0` for ephemeral in-memory-only mode.

### Production API checklist

```bash
export TRUSTEDGE_AGENT_PRODUCTION=1
export TRUSTEDGE_AGENT_ENROLL_TOKEN=<generate-secure-token>
export KAFKA_BROKERS=redpanda:9092
export KAFKA_TOPIC=trustedge.agent.events
```

## Docker / EC2 (TrustEdge compose)

The TrustEdge `docker-compose.yml` profile `agent` runs `trustedge-agent-api` from ECR. Environment is injected by compose — see [AWS deploy](../aws/README.md).

Typical EC2 env (set in TrustEdge compose or `/etc/trustedge/`):

- `TRUSTEDGE_AGENT_PRODUCTION=1`
- `TRUSTEDGE_AGENT_ENROLL_TOKEN` — from `/etc/trustedge/agent-enroll.token`
- `KAFKA_BROKERS` — Redpanda broker inside compose network

## CI

API deploy CI (`.github/workflows/deploy-api.yml`) runs tests, builds the Docker image, pushes to ECR, and deploys to EC2 on push to `develop` or `main`.
