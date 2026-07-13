#!/usr/bin/env bash
# Pull trustedge-agent-api from ECR and (re)start it via TrustEdge docker-compose on EC2.
# Invoked by TrustEdge-Agent GitHub Actions after push to ECR.
set -euo pipefail

TRUSTEDGE_DIR="${TRUSTEDGE_DIR:-$HOME/trustedge}"
ECR_REGISTRY="${ECR_REGISTRY:-804012660077.dkr.ecr.us-east-1.amazonaws.com}"
AWS_REGION="${AWS_REGION:-us-east-1}"

if [ -z "${TRUSTEDGE_AGENT_API_IMAGE:-}" ] && [ -n "${TRUSTTWIN_API_IMAGE:-}" ]; then
  export TRUSTEDGE_AGENT_API_IMAGE="$TRUSTTWIN_API_IMAGE"
fi

if [ -z "${TRUSTEDGE_AGENT_API_IMAGE:-}" ]; then
  echo "ERROR: TRUSTEDGE_AGENT_API_IMAGE is required (full ECR image ref with tag)" >&2
  exit 1
fi

if [ ! -d "$TRUSTEDGE_DIR" ]; then
  echo "ERROR: $TRUSTEDGE_DIR not found. Deploy TrustEdge backend to EC2 first." >&2
  exit 1
fi

cd "$TRUSTEDGE_DIR"

echo "Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "Pulling ${TRUSTEDGE_AGENT_API_IMAGE}..."
docker pull "$TRUSTEDGE_AGENT_API_IMAGE"

export TRUSTEDGE_AGENT_API_IMAGE
chmod +x scripts/ec2-sync-agent-api.sh
bash scripts/ec2-sync-agent-api.sh

export TRUSTEDGE_AGENT_ENROLL_TOKEN
if sudo test -f /etc/trustedge/agent-enroll.token; then
  TRUSTEDGE_AGENT_ENROLL_TOKEN="$(sudo cat /etc/trustedge/agent-enroll.token | tr -d '\r\n')"
elif sudo test -f /etc/trustedge/trusttwin-enroll.token; then
  TRUSTEDGE_AGENT_ENROLL_TOKEN="$(sudo cat /etc/trustedge/trusttwin-enroll.token | tr -d '\r\n')"
else
  echo "ERROR: enroll token not found at /etc/trustedge/agent-enroll.token" >&2
  exit 1
fi

echo "Starting trustedge-agent-api (compose profile: agent)..."
COMPOSE_PROFILES=agent docker compose -f docker-compose.yml up -d --remove-orphans trustedge-agent-api

echo "trustedge-agent-api status:"
COMPOSE_PROFILES=agent docker compose -f docker-compose.yml ps trustedge-agent-api
