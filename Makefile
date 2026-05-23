# MICHA developer convenience targets.
#
# `make help` lists everything. New contributors should be able to run
# `make dev-setup && make test` and have a working environment in
# under 5 minutes.

.PHONY: help dev-setup test test-fast test-coverage lint format \
        check migrate makemigrations runserver shell celery beat \
        frontend-install frontend-build frontend-dev \
        clean docker-build docker-up docker-down docker-logs \
        docker-shell docker-test

# ── Help ──────────────────────────────────────────────────────────

help:
	@echo "MICHA developer commands"
	@echo ""
	@echo "Setup:"
	@echo "  make dev-setup        — install Python + Node deps"
	@echo ""
	@echo "Backend (Django):"
	@echo "  make test             — run the full pytest suite (~30s)"
	@echo "  make test-fast        — run only money-path tests (~25s)"
	@echo "  make test-coverage    — run tests with coverage report"
	@echo "  make lint             — flake8 + black --check"
	@echo "  make format           — black auto-format"
	@echo "  make check            — django manage.py check + makemigrations check"
	@echo "  make migrate          — apply pending migrations"
	@echo "  make makemigrations   — generate migrations"
	@echo "  make runserver        — dev web server on :8000"
	@echo "  make shell            — django shell"
	@echo "  make celery           — celery worker"
	@echo "  make beat             — celery beat scheduler"
	@echo ""
	@echo "Frontend (React + Vite):"
	@echo "  make frontend-install — npm ci"
	@echo "  make frontend-build   — production build (vite)"
	@echo "  make frontend-dev     — dev server on :5173"
	@echo ""
	@echo "Docker (local full-stack: postgres + redis + 4 services):"
	@echo "  make docker-up        — build + start everything"
	@echo "  make docker-down      — stop and remove containers"
	@echo "  make docker-logs      — follow logs from all services"
	@echo "  make docker-shell     — bash inside the web container"
	@echo "  make docker-test      — run pytest inside the container"
	@echo "  make docker-build     — build the image only (no run)"
	@echo ""
	@echo "Utility:"
	@echo "  make clean            — remove caches, dist/, etc."

# ── Setup ─────────────────────────────────────────────────────────

dev-setup:
	@echo "→ Installing Python deps"
	./venv/bin/pip install -r requirements.txt
	./venv/bin/pip install pytest pytest-django pytest-cov
	@echo "→ Installing Node deps"
	cd frontend && npm ci
	@echo ""
	@echo "✓ Setup complete. Run 'make test' to verify."

# ── Backend ───────────────────────────────────────────────────────

# Match what CI runs (see .github/workflows/ci.yml).
TEST_APPS = apps/ledger apps/idempotency apps/inventory apps/fx \
            apps/payments apps/outbox apps/users apps/orders \
            apps/disputes

test:
	MIGRATION_UNSAFE_ALLOWED=1 ./venv/bin/python -m pytest \
	    $(TEST_APPS) \
	    --tb=short

test-fast:
	# Only the 5 hot money paths the audit prioritised.
	MIGRATION_UNSAFE_ALLOWED=1 ./venv/bin/python -m pytest \
	    apps/ledger apps/idempotency apps/inventory \
	    apps/fx apps/payments apps/outbox \
	    --tb=short

test-coverage:
	MIGRATION_UNSAFE_ALLOWED=1 ./venv/bin/python -m pytest \
	    $(TEST_APPS) \
	    --tb=short \
	    --cov=apps \
	    --cov-report=term-missing:skip-covered \
	    --cov-report=html:htmlcov

lint:
	./venv/bin/flake8 apps/ config/ middleware/ \
	    --max-line-length=120 --exclude=migrations \
	    --extend-ignore=E501,W503,E203
	./venv/bin/black --check apps/ config/ middleware/ \
	    --exclude='migrations|node_modules|venv' || true

format:
	./venv/bin/black apps/ config/ middleware/ \
	    --exclude='migrations|node_modules|venv'

check:
	./venv/bin/python manage.py check
	./venv/bin/python manage.py makemigrations --check --dry-run

migrate:
	MIGRATION_UNSAFE_ALLOWED=1 ./venv/bin/python manage.py migrate

makemigrations:
	./venv/bin/python manage.py makemigrations

runserver:
	./venv/bin/python manage.py runserver 0.0.0.0:8000

shell:
	./venv/bin/python manage.py shell

celery:
	./venv/bin/celery -A config worker -l info

beat:
	./venv/bin/celery -A config beat -l info

# ── Frontend ──────────────────────────────────────────────────────

frontend-install:
	cd frontend && npm ci

frontend-build:
	cd frontend && npm run build

frontend-dev:
	cd frontend && npm run dev

# ── Docker (full-stack local) ─────────────────────────────────────

docker-build:
	docker build -f docker/Dockerfile -t micha-backend:dev .

docker-up:
	docker compose up -d --build
	@echo ""
	@echo "✓ MICHA running:"
	@echo "    web      → http://localhost:8000"
	@echo "    daphne   → http://localhost:8001 (websocket)"
	@echo "    postgres → localhost:5432  (micha_dev / micha_user / dev_password_change_me)"
	@echo "    redis    → localhost:6379"
	@echo ""
	@echo "Tail logs:    make docker-logs"
	@echo "Shell in web: make docker-shell"

docker-down:
	docker compose down

docker-down-clean:
	# Also wipe volumes — fresh DB on next docker-up.
	docker compose down -v

docker-logs:
	docker compose logs -f

docker-shell:
	docker compose exec web bash

docker-test:
	docker compose exec -e TEST_DB_POSTGRES=1 web \
	    python -m pytest \
	    apps/ledger apps/idempotency apps/inventory \
	    apps/fx apps/payments apps/outbox \
	    --tb=short

# ── Utility ───────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist frontend/node_modules/.vite
	rm -f coverage.xml .coverage
	rm -rf htmlcov/
	@echo "✓ Cleaned."
