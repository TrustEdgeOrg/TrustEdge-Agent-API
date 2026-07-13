.PHONY: build run test fmt docker-image

build:
	@echo "Python service — use docker-image or run directly"

run:
	python -m app.main

test:
	pytest -q

fmt:
	ruff check app tests || true

docker-image:
	docker build -t trustedge-agent-api .
