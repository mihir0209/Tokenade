.PHONY: help install install-dev test test-quick lint format typecheck clean build docker docker-run test-mut

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install tokenade
	pip install -e .

install-dev:  ## Install with dev dependencies
	pip install -e ".[dev]"
	playwright install chromium --with-deps

test:  ## Run all tests
	python -m pytest tokenade/tests/ -q

test-quick:  ## Run tests without slow/network tests
	python -m pytest tokenade/tests/ -q -m "not slow and not network"

test-verbose:  ## Run tests with verbose output
	python -m pytest tokenade/tests/ -v --tb=short

test-mut:  ## Mutation tests (small high-value slice — prefer over coverage chase)
	@echo "Mutating high-value modules only (see pyproject [tool.mutmut])"
	mutmut run || true
	@echo "Results: mutmut results   Surviving mutants: mutmut show <id>"

lint:  ## Run flake8 linting
	flake8 tokenade --max-line-length=120 --ignore=E501,W503,E203

format:  ## Format code with black
	black tokenade

typecheck:  ## Run mypy type checking
	mypy tokenade --ignore-missing-imports

clean:  ## Clean build artifacts
	rm -rf build dist *.egg-info __pycache__ .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

build:  ## Build distribution packages
	python -m build

docker-build:  ## Build Docker image
	docker build -t tokenade:latest .

docker-run:  ## Run tokenade in Docker
	docker run --rm -it \
		-v $(PWD)/sessions:/app/sessions \
		tokenade:latest

docker-proxy:  ## Run proxy in Docker (usage: make docker-proxy SESSION=foo.tokenade)
	docker run --rm -d \
		--name tokenade-proxy \
		-p 9222:9222 \
		-v $(PWD)/sessions:/app/sessions:ro \
		--cap-add=SYS_ADMIN \
		tokenade:latest proxy --host 0.0.0.0 --port 9222 -s /app/sessions/$(SESSION)

docker-stop:  ## Stop Docker proxy container
	docker stop tokenade-proxy 2>/dev/null || true

docker-cleanup:  ## Remove all tokenade containers
	docker ps -a --filter "name=tokenade" -q | xargs -r docker rm -f

version:  ## Show current version
	@python -c "import tokenade; print(tokenade.__version__)"
