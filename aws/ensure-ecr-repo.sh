#!/bin/bash
# Ensure trustedge-agent-api ECR repository exists (idempotent).
set -euo pipefail

ECR_REPOSITORY="${ECR_REPOSITORY:-trustedge-agent-api}"
AWS_REGION="${AWS_REGION:-us-east-1}"

if aws ecr describe-repositories \
    --repository-names "$ECR_REPOSITORY" \
    --region "$AWS_REGION" \
    --output json >/dev/null 2>&1; then
    echo "[OK] ECR repository '$ECR_REPOSITORY' exists"
else
    echo "Creating ECR repository '$ECR_REPOSITORY'..."
    aws ecr create-repository \
        --repository-name "$ECR_REPOSITORY" \
        --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=false \
        --encryption-configuration encryptionType=AES256 \
        --output json >/dev/null
    echo "[OK] ECR repository created"
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Registry: ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
