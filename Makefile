.PHONY: build run test fmt docker-image

build:
	mkdir -p bin
	go build -buildvcs=false -o bin/trustedge-agent-api ./cmd/trustedge-agent-api

run:
	go run ./cmd/trustedge-agent-api

test:
	go test ./...

fmt:
	go fmt ./...

docker-image:
	docker build -t trustedge-agent-api .
