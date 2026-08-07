.PHONY: up-dev down-dev test-backend test-frontend infra-up

up-dev:
	bash scripts/dev-up.sh

down-dev:
	bash scripts/dev-down.sh

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && npm run build
