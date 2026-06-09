.PHONY: install lint format typecheck test check build

## install: install backend (editable + dev tools) and frontend dependencies
install:
	pip install -e '.[dev]'
	npm install
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
	npm run typecheck --silent

## test: run the backend test suite with coverage
test:
	pytest --cov --cov-report=term-missing

## check: everything CI runs — lint, typecheck, test, build
check: lint typecheck test build

## build: production frontend build (includes tsc)
build:
	npm run build --silent
