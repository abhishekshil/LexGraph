.PHONY: help up down logs build rebuild seed-example query test lint fmt eval eval-gate \
        worker-ingest worker-segment worker-enrich worker-graph worker-index worker-retrieve \
        worker-generate worker-eval project-graph api ui clean

help:
	@echo "LexGraph make targets:"
	@echo "  up                  docker compose up --build"
	@echo "  down                docker compose down -v"
	@echo "  logs                follow all logs"
	@echo "  seed-example        ingest tiny example corpus + private matter"
	@echo "  query Q=\"...\"       send a query to the API"
	@echo "  api                 run FastAPI locally (no docker)"
	@echo "  worker-<name>       run one svc_* worker (see configs/product_services.yml)"
	@echo "  project-graph       AST-only graphify graph -> graphify-out/"
	@echo "  eval                run evaluation suite (report only)"
	@echo "  eval-gate           run evaluation suite with CI regression gate"
	@echo "  test / lint / fmt"

up:
	docker compose -f ops/docker-compose.yml up --build

down:
	docker compose -f ops/docker-compose.yml down -v

logs:
	docker compose -f ops/docker-compose.yml logs -f --tail=200

build:
	docker compose -f ops/docker-compose.yml build

rebuild:
	docker compose -f ops/docker-compose.yml build --no-cache

api:
	uvicorn services.svc_http.main:app --reload --host 0.0.0.0 --port 8080

worker-ingest:
	python -m services.svc_ingest
worker-segment:
	python -m services.svc_segment
worker-enrich:
	python -m services.svc_enrich
worker-graph:
	python -m services.svc_graph_write
worker-index:
	python -m services.svc_index
worker-retrieve:
	python -m services.svc_retrieve
worker-generate:
	python -m services.svc_generate
worker-eval:
	python -m services.svc_eval

project-graph:
	bash scripts/build_project_graph.sh

seed-example:
	python -m scripts.seed_example

query:
	@python -m scripts.ask "$(Q)"

test:
	pytest -q

eval:
	python -m scripts.run_eval --no-gate

eval-gate:
	python -m scripts.run_eval

lint:
	ruff check services tests scripts

fmt:
	ruff format services tests scripts
	ruff check --fix services tests scripts

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
