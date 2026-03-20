.DEFAULT_GOAL := help

# ── Core ────────────────────────────────────────────────────────────────────

build: ## Build the Docker image
	docker compose build

build-nc: ## Build without cache
	docker compose build --no-cache

up: ## Start the stack
	docker compose up -d

down: ## Stop the stack
	docker compose down

restart: ## Restart the runtime container
	docker compose restart openclaw

logs: ## Stream runtime logs
	docker compose logs -f openclaw

ps: ## Show service status
	docker compose ps

# ── CLI ─────────────────────────────────────────────────────────────────────

cli: ## Open an interactive shell in the CLI container
	docker compose --profile cli run --rm openclaw-cli

# ── Setup ───────────────────────────────────────────────────────────────────

onboard: ## Run first-time onboarding
	bash scripts/onboard.sh

validate: ## Validate API keys and tokens
	python3 scripts/validate_credentials.py

health: ## Run health check
	bash scripts/health.sh

# ── Sandboxes ────────────────────────────────────────────────────────────────

sandbox-list: ## List all sandboxes
	bash scripts/sandbox.sh list

sandbox-clone: ## Clone a repo — usage: make sandbox-clone URL=<url> [NAME=<name>]
	bash scripts/sandbox.sh clone $(URL) $(NAME)

sandbox-clean: ## Clean a sandbox — usage: make sandbox-clean NAME=<name>
	bash scripts/sandbox.sh clean $(NAME)

sandbox-reset: ## Reset a sandbox — usage: make sandbox-reset NAME=<name> [URL=<url>]
	bash scripts/sandbox.sh reset $(NAME) $(URL)

# ── Logs ─────────────────────────────────────────────────────────────────────

logs-tail: ## Tail last 50 log lines
	python3 scripts/logs.py tail

logs-errors: ## Show error logs
	python3 scripts/logs.py filter --level error

logs-export: ## Export all logs to a timestamped file
	python3 scripts/logs.py export

logs-prune: ## Prune logs older than 30 days
	python3 scripts/logs.py prune --days 30

# ── Help ─────────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: build build-nc up down restart logs ps cli onboard validate health \
        sandbox-list sandbox-clone sandbox-clean sandbox-reset \
        logs-tail logs-errors logs-export logs-prune help