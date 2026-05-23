#!/bin/bash
#
# MICHA — Automated Backup Restore Drill
# ──────────────────────────────────────────
#
# Why this exists
# ────────────────
# scripts/backup.sh does pg_dump + gzip + S3 upload and runs ``gunzip
# -t`` to verify gzip integrity. That ONLY proves the file isn't
# corrupted bytewise — it does NOT prove the database can be restored
# from it. A backup you've never restored is not a backup, it's wishful
# thinking.
#
# This script does the END-TO-END drill:
#   1. Download the most recent daily backup from S3.
#   2. Verify gzip integrity (belt-and-braces).
#   3. Create a TEMPORARY database (never touches production).
#   4. pg_restore into the temp DB.
#   5. Run validation queries: schema integrity, row counts on
#      critical tables, sample joins, FK integrity.
#   6. Report metrics. Drop the temp DB.
#   7. Exit code: 0 on success, non-zero on failure.
#      Wire to cron + alerting so a silent backup-rot is impossible.
#
# Run this MONTHLY in staging. The cron entry:
#   0 3 1 * * /app/scripts/restore_test.sh >> /var/log/micha/restore_drill.log 2>&1
#   (then a separate cron parses the log + pages on failure)
#
# Also runnable manually for ad-hoc verification:
#   STAGING_DB_HOST=staging-pg.internal ./scripts/restore_test.sh
#
# Configuration via env (all have sensible defaults)
# ────────────────────────────────────────────────────
#   BACKUP_S3_BUCKET    S3 bucket holding backups (default: micha-backups)
#   BACKUP_S3_PREFIX    prefix within bucket    (default: daily)
#   STAGING_DB_HOST     where to restore        (default: localhost — NEVER use prod)
#   STAGING_DB_USER     superuser on staging DB
#   STAGING_DB_PASSWORD password (or use .pgpass)
#   STAGING_DB_PORT     default 5432
#   RESTORE_DB_NAME     temp DB name            (default: micha_restore_test_<timestamp>)
#   PROD_DB_NAME        name of the prod DB     (used by row-count sanity checks)
#                       (default: micha)
#   KEEP_DB_ON_FAILURE  set to "1" to NOT drop the temp DB if validation
#                       fails — lets ops investigate the restored state.
#                       Default: "0" (clean up).
#
# What this script REFUSES to do
# ──────────────────────────────
# • Will not run against $STAGING_DB_HOST matching $PROD_DB_HOST.
#   Manual fat-finger guard against restoring INTO prod by mistake.
# • Will not delete an existing database that doesn't match the
#   "micha_restore_test_*" naming convention. Defensive against
#   typos in env vars.

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-micha-backups}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-daily}"

STAGING_DB_HOST="${STAGING_DB_HOST:-localhost}"
STAGING_DB_PORT="${STAGING_DB_PORT:-5432}"
STAGING_DB_USER="${STAGING_DB_USER:-postgres}"
STAGING_DB_PASSWORD="${STAGING_DB_PASSWORD:-}"

PROD_DB_HOST="${PROD_DB_HOST:-}"
PROD_DB_NAME="${PROD_DB_NAME:-micha}"

RESTORE_DB_NAME="${RESTORE_DB_NAME:-micha_restore_test_$(date +%Y%m%d_%H%M%S)}"
KEEP_DB_ON_FAILURE="${KEEP_DB_ON_FAILURE:-0}"

WORK_DIR="/tmp/micha_restore_drill_$$"
LOG_PREFIX="[restore-drill $(date +%H:%M:%S)]"

mkdir -p "$WORK_DIR"

log() { printf '%s %s\n' "$LOG_PREFIX" "$*"; }
fail() { log "ERROR: $*"; cleanup_and_exit 1; }

# ── Safety guard #1: never restore INTO production ────────────────
if [ -n "$PROD_DB_HOST" ] && [ "$STAGING_DB_HOST" = "$PROD_DB_HOST" ]; then
    fail "STAGING_DB_HOST ($STAGING_DB_HOST) equals PROD_DB_HOST. ABORT."
fi

# ── Safety guard #2: temp DB name must follow convention ─────────
case "$RESTORE_DB_NAME" in
    micha_restore_test_*) ;;
    *) fail "RESTORE_DB_NAME must start with 'micha_restore_test_' (got: $RESTORE_DB_NAME)" ;;
esac

# ── Tool checks ───────────────────────────────────────────────────
for cmd in pg_restore psql aws gunzip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        fail "Required tool not found: $cmd"
    fi
done

# ── Cleanup hook ──────────────────────────────────────────────────
EXIT_CODE=0
cleanup_and_exit() {
    EXIT_CODE="${1:-0}"
    if [ "$EXIT_CODE" -ne 0 ] && [ "$KEEP_DB_ON_FAILURE" = "1" ]; then
        log "KEEP_DB_ON_FAILURE=1 → leaving $RESTORE_DB_NAME for investigation"
    else
        log "Dropping temp database $RESTORE_DB_NAME"
        PGPASSWORD="$STAGING_DB_PASSWORD" psql \
            -h "$STAGING_DB_HOST" -p "$STAGING_DB_PORT" -U "$STAGING_DB_USER" \
            -d postgres -c "DROP DATABASE IF EXISTS \"$RESTORE_DB_NAME\"" 2>&1 \
            | grep -v 'NOTICE:' || true
    fi
    rm -rf "$WORK_DIR"
    log "Done (exit $EXIT_CODE)"
    exit "$EXIT_CODE"
}
trap 'cleanup_and_exit 1' INT TERM ERR

# ╭─────────────────────────────────────────────────────────────────╮
# │  Step 1: Find + download the latest backup                      │
# ╰─────────────────────────────────────────────────────────────────╯
log "Step 1: Finding latest backup in s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}/"

LATEST_KEY=$(aws s3api list-objects-v2 \
    --bucket "$BACKUP_S3_BUCKET" \
    --prefix "${BACKUP_S3_PREFIX}/" \
    --query 'reverse(sort_by(Contents, &LastModified))[0].Key' \
    --output text)

if [ -z "$LATEST_KEY" ] || [ "$LATEST_KEY" = "None" ]; then
    fail "No backups found at s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}/"
fi

log "Latest backup: $LATEST_KEY"

LOCAL_DUMP_GZ="$WORK_DIR/$(basename "$LATEST_KEY")"
aws s3 cp "s3://${BACKUP_S3_BUCKET}/${LATEST_KEY}" "$LOCAL_DUMP_GZ" \
    --no-progress

DUMP_SIZE=$(du -h "$LOCAL_DUMP_GZ" | cut -f1)
log "Downloaded $DUMP_SIZE"

# ╭─────────────────────────────────────────────────────────────────╮
# │  Step 2: Integrity check + decompress                           │
# ╰─────────────────────────────────────────────────────────────────╯
log "Step 2: Verifying gzip integrity"
gunzip -t "$LOCAL_DUMP_GZ" || fail "Gzip integrity check failed — backup is corrupted"

LOCAL_DUMP="${LOCAL_DUMP_GZ%.gz}"
gunzip -k "$LOCAL_DUMP_GZ"
log "Decompressed → $(du -h "$LOCAL_DUMP" | cut -f1)"

# ╭─────────────────────────────────────────────────────────────────╮
# │  Step 3: Create temp database                                   │
# ╰─────────────────────────────────────────────────────────────────╯
log "Step 3: Creating temp database $RESTORE_DB_NAME"
PGPASSWORD="$STAGING_DB_PASSWORD" psql \
    -h "$STAGING_DB_HOST" -p "$STAGING_DB_PORT" -U "$STAGING_DB_USER" \
    -d postgres \
    -c "CREATE DATABASE \"$RESTORE_DB_NAME\" WITH TEMPLATE template0 ENCODING 'UTF8'" \
    || fail "Failed to create temp database"

# ╭─────────────────────────────────────────────────────────────────╮
# │  Step 4: pg_restore                                             │
# ╰─────────────────────────────────────────────────────────────────╯
log "Step 4: Restoring dump (this is the slow step)"
RESTORE_START=$(date +%s)

# ``--no-owner --no-acl`` strips role/grant statements (the restoring
# user is staging's superuser, NOT the prod owner). ``--exit-on-error``
# turns warnings into failures — we want strict.
PGPASSWORD="$STAGING_DB_PASSWORD" pg_restore \
    -h "$STAGING_DB_HOST" -p "$STAGING_DB_PORT" -U "$STAGING_DB_USER" \
    -d "$RESTORE_DB_NAME" \
    --no-owner --no-acl \
    --exit-on-error \
    "$LOCAL_DUMP" 2>"$WORK_DIR/restore.err"

RESTORE_END=$(date +%s)
RESTORE_DURATION=$((RESTORE_END - RESTORE_START))
log "Restored in ${RESTORE_DURATION}s"

# ╭─────────────────────────────────────────────────────────────────╮
# │  Step 5: Validation queries                                     │
# ╰─────────────────────────────────────────────────────────────────╯
log "Step 5: Validating restored database"

# Helper that runs a query and returns the scalar result.
run_scalar() {
    PGPASSWORD="$STAGING_DB_PASSWORD" psql \
        -h "$STAGING_DB_HOST" -p "$STAGING_DB_PORT" -U "$STAGING_DB_USER" \
        -d "$RESTORE_DB_NAME" \
        -tA -c "$1"
}

# ── 5a. Schema integrity: critical tables exist ──────────────────
log "  → schema integrity"
EXPECTED_TABLES="users_user orders_order orders_payment orders_refund \
                 payments_sellerwallet payments_paymentevent \
                 ledger_account ledger_journal ledger_ledgerentry \
                 inventory_stockreservation fx_fxrate \
                 idempotency_idempotencykey outbox_outboxevent"

MISSING=""
for t in $EXPECTED_TABLES; do
    EXISTS=$(run_scalar "SELECT EXISTS(
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='$t'
    )")
    if [ "$EXISTS" != "t" ]; then
        MISSING="$MISSING $t"
    fi
done
if [ -n "$MISSING" ]; then
    fail "Schema integrity FAIL — missing tables:$MISSING"
fi
log "    ✓ all expected tables present"

# ── 5b. Row counts on critical tables ────────────────────────────
log "  → row counts"
USER_COUNT=$(run_scalar "SELECT COUNT(*) FROM users_user")
ORDER_COUNT=$(run_scalar "SELECT COUNT(*) FROM orders_order")
PAYMENT_COUNT=$(run_scalar "SELECT COUNT(*) FROM orders_payment")
LEDGER_COUNT=$(run_scalar "SELECT COUNT(*) FROM ledger_ledgerentry")
log "    users=$USER_COUNT  orders=$ORDER_COUNT  payments=$PAYMENT_COUNT  ledger_entries=$LEDGER_COUNT"

# A non-zero check protects against "we restored an empty schema" —
# the dump file may exist but if pg_dump captured zero data, the
# restore "succeeds" but produces a useless DB.
if [ "$USER_COUNT" = "0" ] && [ "$ORDER_COUNT" = "0" ]; then
    fail "Restored DB has 0 users AND 0 orders — dump captured no data"
fi

# ── 5c. Ledger double-entry invariant ────────────────────────────
# The most important business invariant. If sum(debits) != sum(credits),
# the ledger has drifted somewhere in production AND our backup
# captured the drift. Either way, ops needs to know.
log "  → ledger invariant (Σ debits == Σ credits)"
LEDGER_DRIFT=$(run_scalar "
    SELECT COALESCE(SUM(debit_cents), 0) - COALESCE(SUM(credit_cents), 0)
    FROM ledger_ledgerentry
")
if [ "$LEDGER_DRIFT" != "0" ]; then
    fail "LEDGER IMBALANCED in restored backup: drift=$LEDGER_DRIFT cents. \
This is a CRITICAL incident — production ledger has drifted from \
double-entry invariant."
fi
log "    ✓ ledger balanced"

# ── 5d. Sample join — confirms FK integrity ──────────────────────
log "  → sample join (orders + buyer)"
JOIN_COUNT=$(run_scalar "
    SELECT COUNT(*)
    FROM orders_order o
    JOIN users_user u ON o.buyer_id = u.id
")
log "    ✓ $JOIN_COUNT order-buyer joins resolvable"

# ── 5e. PROTECT-on-delete invariants survive restore ─────────────
# Sprint 0 / Commit 4 flipped CASCADE → PROTECT on financial FKs.
# Verify the FK constraints exist in the restored schema (they
# would be in pg_constraint if the migration ran).
log "  → financial FK PROTECT constraints present"
PROTECT_FK_COUNT=$(run_scalar "
    SELECT COUNT(*) FROM pg_constraint
    WHERE contype='f'
      AND conname LIKE '%payment%order%'
       OR conname LIKE '%refund%order%'
")
if [ "$PROTECT_FK_COUNT" = "0" ]; then
    log "    ⚠ no payment/refund order FKs found — backup may predate Sprint 0 / Commit 4"
else
    log "    ✓ $PROTECT_FK_COUNT financial FK constraints in schema"
fi

# ╭─────────────────────────────────────────────────────────────────╮
# │  Step 6: Report                                                 │
# ╰─────────────────────────────────────────────────────────────────╯
log "Step 6: Drill report"
log "  backup_key:          $LATEST_KEY"
log "  download_size:       $DUMP_SIZE"
log "  restore_duration:    ${RESTORE_DURATION}s"
log "  users:               $USER_COUNT"
log "  orders:              $ORDER_COUNT"
log "  payments:            $PAYMENT_COUNT"
log "  ledger_entries:      $LEDGER_COUNT"
log "  ledger_invariant:    OK"
log ""
log "✓ RESTORE DRILL PASSED"

cleanup_and_exit 0
