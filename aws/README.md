# TrustEdge Agent API — AWS CI

The **Build and Deploy trustedge-agent-api** workflow (`.github/workflows/deploy-api.yml`) builds the image, pushes to ECR, and starts the container on EC2 via TrustEdge `docker-compose.yml`.

## GitHub secrets

Workflows use `${{ secrets.NAME }}`. **Repository secrets** always work. **Organization secrets** require a paid GitHub plan for **private** repos — on **GitHub Free**, org secrets are silently empty in private repo workflows.

### TrustEdge Agent API (required — repository secrets)

**TrustEdgeOrg/TrustEdge-Agent-API → Settings → Secrets and variables → Actions → Repository secrets** (not Organization secrets):

| Secret | Value |
|--------|--------|
| `AWS_ROLE_ARN` | `arn:aws:iam::804012660077:role/GitHubActionsDeployRole` |
| `EC2_HOST` | `44.218.45.174` |
| `EC2_SSH_KEY` | Full private key (`cat ~/.ssh/id_rsa`) |

Use the **Secrets** tab, not **Variables**.

### Organization secrets (optional — paid plan only)

If your org is on **Team** or higher, you may share secrets across TrustEdge + TrustEdge Agent API at org level instead. On **GitHub Free**, org secrets will not work for private repos — use repository secrets per repo.

## One-time AWS setup

From the **TrustEdge** repo (with AWS admin credentials):

```bash
bash aws/update-github-actions-trust-policy.sh
```

Add `TrustEdgeOrg/TrustEdge-Agent-API` to the OIDC trust policy so it can assume `GitHubActionsDeployRole` for ECR push.

## EC2 prerequisites

- TrustEdge deployed at `~/trustedge` (backend, redpanda running).
- EC2 instance role can call `aws ecr get-login-password` and pull from ECR.
- Security group allows SSH (port 22) from GitHub Actions runners.

## Trigger a deploy

Push to `develop` or `main`, or run **Build and Deploy trustedge-agent-api** manually.

- `develop` → pushes `:develop`, runs container with that tag
- `main` → pushes `:latest`, runs container with that tag

## Verify on EC2

```bash
aws ecr list-images --repository-name trustedge-agent-api --region us-east-1
cd ~/trustedge && COMPOSE_PROFILES=agent docker compose ps trustedge-agent-api
curl -s http://127.0.0.1:8080/healthz
```

## Local EC2 deploy script

After a manual `docker push`:

```bash
export TRUSTEDGE_AGENT_API_IMAGE=804012660077.dkr.ecr.us-east-1.amazonaws.com/trustedge-agent-api:develop
bash aws/ec2-deploy-api.sh
```

The script auto-detects whether the EC2 TrustEdge checkout still uses the legacy
`trusttwin-api` compose profile or the renamed `trustedge-agent-api` / `agent` profile.
