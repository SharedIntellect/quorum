#!/usr/bin/env bash
# backup.sh — nightly database and config backup script
# Usage: ./backup.sh [--full | --incremental]
# Runs via cron: 02:00 UTC daily
#
# Managed by: ops@company.internal
# Last updated: 2026-02-03

BACKUP_MODE="${1:---incremental}"
BACKUP_DIR="/mnt/backups/$(date +%Y%m%d)"
DB_HOST="db-primary.company.internal"
DB_PORT=5432
DB_NAME="appdb"
DB_USER="backup_user"
CONFIG_SOURCE="/etc/appconfig"
RETENTION_DAYS=30
S3_BUCKET="s3://company-backups/db"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Preparation ───────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
log "Backup started. Mode: $BACKUP_MODE  Dir: $BACKUP_DIR"

# ── Database dump ─────────────────────────────────────────────────────────────

if [[ "$BACKUP_MODE" == "--full" ]]; then
    DUMP_FILE="${BACKUP_DIR}/${DB_NAME}-full-$(date +%H%M%S).sql.gz"
    log "Running full pg_dump → $DUMP_FILE"
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" \
        | gzip > "$DUMP_FILE"
else
    DUMP_FILE="${BACKUP_DIR}/${DB_NAME}-incr-$(date +%H%M%S).sql.gz"
    log "Running incremental pg_dump → $DUMP_FILE"
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" \
        --table=audit_log --table=events \
        | gzip > "$DUMP_FILE"
fi

log "Database dump complete: $DUMP_FILE"

# ── Config snapshot ───────────────────────────────────────────────────────────

CONFIG_ARCHIVE="${BACKUP_DIR}/config-$(date +%H%M%S).tar.gz"
tar -czf "$CONFIG_ARCHIVE" "$CONFIG_SOURCE"
log "Config snapshot: $CONFIG_ARCHIVE"

# ── Upload to S3 ──────────────────────────────────────────────────────────────

log "Uploading to $S3_BUCKET..."
aws s3 sync "$BACKUP_DIR" "$S3_BUCKET/$(date +%Y%m%d)/" \
    --sse aws:kms \
    --storage-class STANDARD_IA

# ── Prune old local backups ───────────────────────────────────────────────────

log "Pruning local backups older than ${RETENTION_DAYS} days..."
OLD_DIR=$(find /mnt/backups -maxdepth 1 -type d -mtime +${RETENTION_DAYS} | head -1)
rm -rf $OLD_DIR

log "Backup complete."
