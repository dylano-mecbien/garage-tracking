#!/bin/bash
# ============================================================
# Script de sauvegarde GarageApp — DB PostgreSQL + MinIO
# À placer sur le serveur : /home/deploy/backups/scripts/backup.sh
# ============================================================

set -e  # Arrête le script au premier échec

# ── Configuration (à adapter) ──────────────────────────────
PROJECT_DIR="/home/deploy/garage-suivi"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
DB_CONTAINER="db"
DB_USER="garage_user"
DB_NAME="garage_db"
MINIO_VOLUME="suivi_garage_minio_data"   # ajuste selon le vrai nom (voir note ci-dessous)

BACKUP_ROOT="/home/deploy/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$BACKUP_ROOT/backup.log"

DB_RETENTION_DAYS=14      # garde 14 jours de backups DB
MINIO_RETENTION_COUNT=7   # garde les 7 derniers backups MinIO (plus volumineux)

echo "===== Backup démarré: $(date) =====" >> "$LOG_FILE"

# ── 1. Sauvegarde PostgreSQL ───────────────────────────────
DB_BACKUP_DIR="$BACKUP_ROOT/db"
mkdir -p "$DB_BACKUP_DIR"

echo "Sauvegarde de la base de données..." >> "$LOG_FILE"
docker compose -f "$COMPOSE_FILE" exec -T "$DB_CONTAINER" \
  pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DB_BACKUP_DIR/garage_db_$TIMESTAMP.sql.gz"

if [ $? -eq 0 ]; then
  echo "✅ Backup DB réussi: garage_db_$TIMESTAMP.sql.gz" >> "$LOG_FILE"
else
  echo "❌ ÉCHEC backup DB" >> "$LOG_FILE"
fi

# Rotation : supprime les backups DB de plus de X jours
find "$DB_BACKUP_DIR" -name "*.sql.gz" -mtime +$DB_RETENTION_DAYS -delete

# ── 2. Sauvegarde MinIO ─────────────────────────────────────
MINIO_BACKUP_DIR="$BACKUP_ROOT/minio/$TIMESTAMP"
mkdir -p "$MINIO_BACKUP_DIR"

echo "Sauvegarde de MinIO..." >> "$LOG_FILE"
docker run --rm \
  -v "$MINIO_VOLUME":/source:ro \
  -v "$MINIO_BACKUP_DIR":/backup \
  alpine cp -r /source/. /backup/

if [ $? -eq 0 ]; then
  echo "✅ Backup MinIO réussi: $TIMESTAMP" >> "$LOG_FILE"
else
  echo "❌ ÉCHEC backup MinIO" >> "$LOG_FILE"
fi

# Rotation : garde seulement les N derniers backups MinIO
ls -dt "$BACKUP_ROOT"/minio/*/ 2>/dev/null | tail -n +$((MINIO_RETENTION_COUNT + 1)) | xargs -r rm -rf

echo "===== Backup terminé: $(date) =====" >> "$LOG_FILE"

# ── 3. Synchronisation vers un stockage externe (rclone) ────
# Nécessite une config rclone préalable : `rclone config`
# Remplace "monstockage" par le nom donné lors de la config rclone.
echo "Synchronisation vers le stockage externe..." >> "$LOG_FILE"
rclone sync "$BACKUP_ROOT/db" monstockage:garage-backups/db --log-file="$LOG_FILE" --log-level INFO
rclone sync "$BACKUP_ROOT/minio" monstockage:garage-backups/minio --log-file="$LOG_FILE" --log-level INFO

echo "===== Synchronisation externe terminée: $(date) =====" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
