# TrustEdge Agent API

Ingest API for the [TrustEdge](https://github.com/TrustEdgeOrg/TrustEdge) security observability platform. Endpoint agents POST telemetry here; optionally publishes to Kafka for detection.

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
pip install -r requirements-dev.txt
python -m app.main
```

With Kafka (optional):

```bash
export KAFKA_BROKERS=127.0.0.1:9092
python -m app.main
```

Point the agent at this API:

```bash
cd ~/Desktop/TrustEdge-Agent
export TRUSTEDGE_AGENT_API_URL=http://127.0.0.1:8080
go run ./cmd/trustedge-agent
```

## Build

Requires **Python 3.12+**.

```bash
pip install -r requirements-dev.txt
make test
```

## Deploy (ECR → EC2)

CI (`.github/workflows/deploy-api.yml`) builds the Docker image, pushes to ECR, and deploys to EC2 via TrustEdge `docker-compose.yml`.

See [aws/README.md](aws/README.md) for secrets and one-time setup.

## Project layout

```text
app/                       # FastAPI ingest service
  main.py                  # App entry + uvicorn
  routes.py                # HTTP handlers
  store.py                 # Memory, disk, Kafka
  kafka_publisher.py       # Event publisher
docs/                      # API reference
tests/                     # pytest suite
```
