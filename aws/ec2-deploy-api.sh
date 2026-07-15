#!/usr/bin/env bash
# Pull trustedge-agent-api from ECR and (re)start it via TrustEdge docker-compose on EC2.
# Works with both:
#   - modern compose: profile agent / service trustedge-agent-api
#   - legacy compose: profile trusttwin / service trusttwin-api
set -euo pipefail

TRUSTEDGE_DIR="${TRUSTEDGE_DIR:-$HOME/trustedge}"
ECR_REGISTRY="${ECR_REGISTRY:-804012660077.dkr.ecr.us-east-1.amazonaws.com}"
AWS_REGION="${AWS_REGION:-us-east-1}"

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

# Detect compose layout on this host.
if grep -qE '^[[:space:]]*trustedge-agent-api:' docker-compose.yml 2>/dev/null; then
  MODE=agent
elif grep -qE '^[[:space:]]*trusttwin-api:' docker-compose.yml 2>/dev/null; then
  MODE=trusttwin
else
  echo "ERROR: neither trustedge-agent-api nor trusttwin-api found in docker-compose.yml" >&2
  exit 1
fi
echo "Detected compose mode: ${MODE}"

upsert_env() {
  local key="$1"
  local val="$2"
  local file="$3"
  touch "$file"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed -i.bak "s|^${key}=.*|${key}=${val}|" "$file" && rm -f "${file}.bak"
  else
    echo "${key}=${val}" >>"$file"
  fi
}

if [ -f scripts/ec2-sync-agent-api.sh ] && [ "$MODE" = agent ]; then
  export TRUSTEDGE_AGENT_API_IMAGE
  chmod +x scripts/ec2-sync-agent-api.sh
  bash scripts/ec2-sync-agent-api.sh
elif [ -f scripts/ec2-sync-trusttwin.sh ] && [ "$MODE" = trusttwin ]; then
  export TRUSTTWIN_API_IMAGE="$TRUSTEDGE_AGENT_API_IMAGE"
  chmod +x scripts/ec2-sync-trusttwin.sh
  bash scripts/ec2-sync-trusttwin.sh
else
  echo "WARNING: no sync script for mode=${MODE}; writing image into .env directly"
  if [ "$MODE" = agent ]; then
    upsert_env "TRUSTEDGE_AGENT_API_IMAGE" "$TRUSTEDGE_AGENT_API_IMAGE" .env
  else
    upsert_env "TRUSTTWIN_API_IMAGE" "$TRUSTEDGE_AGENT_API_IMAGE" .env
  fi
fi

if [ "$MODE" = agent ]; then
  if sudo test -f /etc/trustedge/agent-enroll.token; then
    export TRUSTEDGE_AGENT_ENROLL_TOKEN
    TRUSTEDGE_AGENT_ENROLL_TOKEN="$(sudo cat /etc/trustedge/agent-enroll.token | tr -d '\r\n')"
  elif sudo test -f /etc/trustedge/trusttwin-enroll.token; then
    export TRUSTEDGE_AGENT_ENROLL_TOKEN
    TRUSTEDGE_AGENT_ENROLL_TOKEN="$(sudo cat /etc/trustedge/trusttwin-enroll.token | tr -d '\r\n')"
  else
    echo "ERROR: enroll token not found under /etc/trustedge/" >&2
    exit 1
  fi
  echo "Starting trustedge-agent-api (compose profile: agent)..."
  COMPOSE_PROFILES=agent docker compose -f docker-compose.yml up -d --remove-orphans --force-recreate trustedge-agent-api
  COMPOSE_PROFILES=agent docker compose -f docker-compose.yml ps trustedge-agent-api
else
  export TRUSTTWIN_API_IMAGE="$TRUSTEDGE_AGENT_API_IMAGE"
  if sudo test -f /etc/trustedge/trusttwin-enroll.token; then
    export TRUSTTWIN_ENROLL_TOKEN
    TRUSTTWIN_ENROLL_TOKEN="$(sudo cat /etc/trustedge/trusttwin-enroll.token | tr -d '\r\n')"
  elif sudo test -f /etc/trustedge/agent-enroll.token; then
    export TRUSTTWIN_ENROLL_TOKEN
    TRUSTTWIN_ENROLL_TOKEN="$(sudo cat /etc/trustedge/agent-enroll.token | tr -d '\r\n')"
  else
    echo "ERROR: enroll token not found under /etc/trustedge/" >&2
    exit 1
  fi
  echo "Starting trusttwin-api with Agent API image (compose profile: trusttwin)..."
  COMPOSE_PROFILES=trusttwin docker compose -f docker-compose.yml up -d --remove-orphans --force-recreate trusttwin-api
  COMPOSE_PROFILES=trusttwin docker compose -f docker-compose.yml ps trusttwin-api
fi
