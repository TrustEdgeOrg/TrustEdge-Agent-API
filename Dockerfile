# Production image for trustedge-agent-api (ingest gateway only — not the laptop agent).
FROM golang:1.22-alpine AS build

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -buildvcs=false -trimpath -ldflags="-s -w" \
    -o /trustedge-agent-api ./cmd/trustedge-agent-api

FROM alpine:3.20

RUN apk add --no-cache ca-certificates wget \
    && adduser -D -H -u 10001 app

WORKDIR /data

COPY --from=build /trustedge-agent-api /usr/local/bin/trustedge-agent-api

USER app

EXPOSE 8080

ENV TRUSTEDGE_AGENT_LISTEN=:8080 \
    TRUSTEDGE_AGENT_DATA_DIR=/data

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O- http://127.0.0.1:8080/healthz >/dev/null || exit 1

ENTRYPOINT ["trustedge-agent-api"]
