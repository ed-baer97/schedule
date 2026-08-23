#!/usr/bin/env bash
# Daily Postgres dump for the Docker stand.
# Cron example (on the Ubuntu host):
#   15 3 * * * /opt/schedule/deploy/backup-postgres.sh >> /var/log/schedule-backup.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/school_schedule_${STAMP}.sql.gz"

docker compose exec -T db \
  pg_dump -U "${POSTGRES_USER:-schedule}" "${POSTGRES_DB:-school_schedule}" \
  | gzip > "$OUT"

# Keep last 14 dumps
ls -1t "$BACKUP_DIR"/school_schedule_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Wrote $OUT"
