# TrustEdge Agent API

Ingest API for the [TrustEdge](https://github.com/TrustEdgeOrg/TrustEdge) security observability platform. Endpoint agents POST telemetry here; production mode mirrors to Redis and publishes to Kafka for detection.

Pairs with [TrustEdge-Agent](https://github.com/TrustEdgeOrg/TrustEdge-Agent) (cross-platform endpoint agent).

## Documentation

| Guide | Description |
|-------|-------------|
| [API reference](docs/api.md) | HTTP endpoints and event payloads |
| [Configuration](docs/configuration.md) | Environment variables |
| [AWS deploy](aws/README.md) | ECR build and EC2 deploy |

## Quick start (local)

```bash
cd ~/Desktop/TrustEdge-Agent-API
go run ./cmd/trustedge-agent-api
```

With Redis and Kafka (TrustEdge dev stack):

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
export KAFKA_BROKERS=127.0.0.1:9092
go run ./cmd/trustedge-agent-api
```

Point the agent at this API:

```bash
cd ~/Desktop/TrustEdge-Agent
export TRUSTEDGE_AGENT_API_URL=http://127.0.0.1:8080
go run ./cmd/trustedge-agent
```

## Build

```bash
make build   # → bin/trustedge-agent-api
make test
```

## Deploy (ECR → EC2)

CI (`.github/workflows/deploy-api.yml`) builds the Docker image, pushes to ECR, and deploys to EC2 via TrustEdge `docker-compose.yml`.

See [aws/README.md](aws/README.md) for secrets and one-time setup.

## Project layout

```text
cmd/trustedge-agent-api/   # HTTP ingest service
internal/server/           # Route handlers
internal/store/            # Memory, disk, Redis, Kafka
internal/kafka/            # Event publisher
docs/                      # API reference
```
