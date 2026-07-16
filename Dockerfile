# Production image for trustedge-agent-api (ingest gateway only — not the laptop agent).
FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache ca-certificates wget

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

RUN adduser -D -H -u 10001 app \
    && mkdir -p /data \
    && chown app:app /data

USER app

# Keep code WORKDIR at /app so `python -m app.main` resolves without relying on PYTHONPATH.
# Persist agent state under TRUSTEDGE_AGENT_DATA_DIR (/data), not the process cwd.
EXPOSE 8080

ENV TRUSTEDGE_AGENT_LISTEN=:8080 \
    TRUSTEDGE_AGENT_DATA_DIR=/data \
    PYTHONPATH=/app

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O- http://127.0.0.1:8080/healthz >/dev/null || exit 1

CMD ["python", "-m", "app.main"]
