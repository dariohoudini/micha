# MICHA developer convenience targets.
#
# `make help` lists everything. New contributors should be able to run
# `make dev-setup && make test` and have a working environment in
# under 5 minutes.

.PHONY: help dev-setup test test-fast test-coverage lint format \
        check migrate makemigrations runserver shell celery beat \
        frontend-install frontend-build frontend-dev \
        phone phone-ios phone-ios-refresh phone-ios-reset \
        phone-android-setup phone-android \
        clean docker-build docker-up docker-down docker-logs \
        docker-shell docker-test \
        restore-drill

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
	@echo "Phone testing (try the app on your own device):"
	@echo "  make phone            — open in mobile browser over WiFi"
	@echo "  make phone-ios        — build + open Xcode (one-shot setup)"
	@echo "  make phone-ios-refresh — re-sync LAN IP into Capacitor (after WiFi change)"
	@echo "  make phone-ios-reset  — revert capacitor.config to prod-safe"
	@echo "  make phone-android-setup  — one-time Android project init"
	@echo "  make phone-android    — build + open Android native shell"
	@echo ""
	@echo "Docker (local full-stack: postgres + redis + 4 services):"
	@echo "  make docker-up        — build + start everything"
	@echo "  make docker-down      — stop and remove containers"
	@echo "  make docker-logs      — follow logs from all services"
	@echo "  make docker-shell     — bash inside the web container"
	@echo "  make docker-test      — run pytest inside the container"
	@echo "  make docker-build     — build the image only (no run)"
	@echo ""
	@echo "Operations:"
	@echo "  make restore-drill    — validate S3 backups by restoring + querying"
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
	# Bug-only check (BLOCKING) — matches the CI gate. Real runtime
	# errors: syntax, undefined names, bad imports.
	./venv/bin/python -m flake8 apps/ config/ middleware/ \
	    --max-line-length=120 --exclude=migrations \
	    --select=E9,F63,F7,F82,F821
	# Style check (NON-blocking) — surfaces pre-existing tech debt.
	./venv/bin/python -m flake8 apps/ config/ middleware/ \
	    --max-line-length=120 --exclude=migrations \
	    --extend-ignore=E501,W503,E203 \
	    --statistics --count || true
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

phone:
	# Launch backend + frontend bound to all interfaces so your phone
	# (on the same WiFi) can access the dev server. Prints the URL to
	# type on your phone. See ops/PHONE_DEV.md for full instructions.
	./scripts/dev-phone.sh

phone-ios:
	# Full iOS setup: xcode-select switch + CocoaPods install +
	# Capacitor live-reload config + build + open Xcode.
	# Run `make phone` in another terminal FIRST so the dev server
	# is up. See ops/PHONE_DEV.md for full instructions.
	./scripts/dev-phone-ios.sh

phone-ios-refresh:
	# Switched WiFi / woke from sleep / blank page in the iOS sim?
	# Re-detects the LAN IP, updates capacitor.config.json, and
	# runs cap sync. No CocoaPods, no Xcode reopen — fast.
	# After it runs: Cmd+R in Xcode to relaunch the app.
	./scripts/dev-phone-ios.sh --refresh

phone-ios-reset:
	# Revert capacitor.config.json to production-safe (removes the
	# dev server.url). Run before building a production .ipa.
	./scripts/dev-phone-ios.sh --reset

phone-android-setup:
	# One-time Android setup. Requires Android Studio + ANDROID_HOME.
	cd frontend && npx cap add android && npx cap sync android
	@echo ""
	@echo "✓ Android project created. Run: make phone-android"

phone-android:
	cd frontend && npm run build && npx cap sync android && npx cap open android

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

# ── Operations ────────────────────────────────────────────────────

restore-drill:
	# Validates the most recent S3 backup by actually restoring it
	# into a temp DB on STAGING_DB_HOST and running the invariant
	# queries (ledger balance, schema integrity, row counts).
	#
	# Required env vars (see scripts/restore_test.sh for full list):
	#   BACKUP_S3_BUCKET, STAGING_DB_HOST, STAGING_DB_USER,
	#   STAGING_DB_PASSWORD, AWS credentials.
	#
	# Run monthly via cron in staging. Failure exits non-zero so
	# the cron alerting hook pages on-call.
	./scripts/restore_test.sh

# ── Utility ───────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist frontend/node_modules/.vite
	rm -f coverage.xml .coverage
	rm -rf htmlcov/
	@echo "✓ Cleaned."
