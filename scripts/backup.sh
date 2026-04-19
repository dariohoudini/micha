#!/bin/bash
# MICHA — Automated Database Backup
# FIX: No backup automation was in place. One accidental DELETE * = all data gone.
# Run this via cron: 0 2 * * * /app/scripts/backup.sh
# Keeps 30 daily backups, 12 monthly backups.

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
DB_NAME="${DB_NAME:-micha}"
DB_USER="${DB_USER:-micha_user}"
DB_HOST="${DB_HOST:-localhost}"
S3_BUCKET="${BACKUP_S3_BUCKET:-micha-backups}"
BACKUP_DIR="/tmp/micha_backups"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup of $DB_NAME..."

# ── Dump database ─────────────────────────────────────────────────────────────
BACKUP_FILE="$BACKUP_DIR/micha_${TIMESTAMP}.dump"
PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -Fc \
    --no-password \
    -f "$BACKUP_FILE"

echo "[$(date)] Dump complete: $BACKUP_FILE ($(du -sh $BACKUP_FILE | cut -f1))"

# ── Compress ──────────────────────────────────────────────────────────────────
gzip "$BACKUP_FILE"
BACKUP_FILE="${BACKUP_FILE}.gz"

# ── Upload to S3 ──────────────────────────────────────────────────────────────
# Daily backup
aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/daily/micha_${DATE}.dump.gz" \
    --storage-class STANDARD_IA

# Monthly backup (first day of month)
if [ "$(date +%d)" = "01" ]; then
    aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/monthly/micha_$(date +%Y-%m).dump.gz" \
        --storage-class GLACIER
    echo "[$(date)] Monthly backup uploaded to Glacier"
fi

echo "[$(date)] Upload complete: s3://${S3_BUCKET}/daily/micha_${DATE}.dump.gz"

# ── Clean old backups ─────────────────────────────────────────────────────────
# Keep 30 daily backups
aws s3 ls "s3://${S3_BUCKET}/daily/" \
    | sort \
    | head -n -30 \
    | awk '{print $4}' \
    | xargs -I {} aws s3 rm "s3://${S3_BUCKET}/daily/{}" || true

# ── Clean local temp ──────────────────────────────────────────────────────────
rm -f "$BACKUP_FILE"

echo "[$(date)] Backup complete. Duration: $SECONDS seconds"

# ── Verify backup integrity ───────────────────────────────────────────────────
echo "[$(date)] Verifying backup..."
VERIFY_FILE="/tmp/micha_verify.dump.gz"
aws s3 cp "s3://${S3_BUCKET}/daily/micha_${DATE}.dump.gz" "$VERIFY_FILE"
gunzip -t "$VERIFY_FILE" && echo "[$(date)] Backup verified OK" || echo "[$(date)] ERROR: Backup verification FAILED"
rm -f "$VERIFY_FILE"
