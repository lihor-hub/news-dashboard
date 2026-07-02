.PHONY: install ci-install lint format typecheck \
        test test-smoke test-backend test-frontend test-e2e test-a11y test-nightly test-full \
        helm-validate check build

## install: install backend (editable + dev tools) and update local frontend dependencies
install:
	pip install -e '.[dev]'
	npm install
	pre-commit install

## ci-install: install backend and exact frontend dependencies from package-lock.json
ci-install:
	pip install -e '.[dev]'
	npm ci
	pre-commit install

## lint: run all linters without modifying files
lint:
	ruff check backend
	ruff format --check backend
	npm run lint --silent
	npm run format:check --silent

## format: auto-format backend and frontend code
format:
	ruff check backend --fix
	ruff format backend
	npm run lint:fix --silent
	npm run format --silent

## typecheck: run static type checkers
typecheck:
	mypy backend
	PYTHONPATH=.:backend ty check backend
	pyrefly check backend
	npm run typecheck --silent

## test: run backend + frontend test suites (everyday development loop)
test:
	pytest --cov --cov-report=term-missing
	npm run test:frontend --silent

## test-smoke: fast smoke tests — backend health + core API paths, frontend app render
test-smoke:
	pytest -m smoke -v
	npm run test:frontend:smoke --silent

## test-backend: all backend pytest tests
test-backend:
	pytest -v

## test-frontend: all frontend Vitest tests
test-frontend:
	npm run test:frontend --silent

## test-e2e: Playwright end-to-end tests
test-e2e:
	npm run test:e2e --silent

## test-a11y: accessibility smoke tests (axe-core serious/critical violations)
test-a11y:
	npm run test:a11y --silent

## test-nightly: full suite with coverage — same as what the nightly CI runs
test-nightly:
	pytest --cov --cov-report=term-missing --cov-report=html -v
	npm run test:frontend:coverage --silent

## test-full: alias for test-nightly (complete suite with coverage)
test-full: test-nightly

## helm-validate: lint and render the Helm chart with default and production-like values
helm-validate:
	helm lint ./helm/news-dashboard
	helm template news-dashboard ./helm/news-dashboard \
		--set-string "app.auth.sessionSecret=dummy-session-secret-for-render-only"
	helm template news-dashboard ./helm/news-dashboard \
		--set "image.tag=abc1234" \
		--set "image.pullSecretName=ghcr-pull-secret" \
		--set "service.type=NodePort" \
		--set "service.nodePort=30088" \
		--set-string "app.auth.sessionSecret=dummy-session-secret-for-render-only" \
		--set "app.ai.existingSecret=news-dashboard-ai" \
		--set "app.push.existingSecret=news-dashboard-push" \
		--set-string "app.ai.freeLlmBaseUrl=http://192.168.0.75:9130/v1" \
		--set-string "app.ai.briefingModel=gpt-4o" \
		--set-string "app.ai.langfuse.host=http://langfuse.local" \
		--set-string "app.push.email=test@example.com" \
		--set "postgresql.persistence.hostPath=/home/ioachim-minipc/news-dashboard-postgres-data"
	helm template news-dashboard ./helm/news-dashboard \
		--set "postgresql.enabled=false" \
		--set "app.databaseUrl.existingSecret=news-dashboard-db" \
		--set-string "app.auth.sessionSecret=dummy-session-secret-for-render-only"

## check: everything CI runs — lint, typecheck, test, build
check: lint typecheck test build

## build: production frontend build (includes tsc)
build:
	npm run build --silent
