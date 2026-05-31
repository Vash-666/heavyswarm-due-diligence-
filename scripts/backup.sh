#!/bin/sh
# HeavySwarm Database Backup Script
# =============================================================================

set -e

# Configuration
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/diligence_backup_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}

# Create backup
echo "Starting database backup at $(date)"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "${POSTGRES_HOST}" \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --verbose \
    --no-owner \
    --no-privileges \
    | gzip > "${BACKUP_FILE}"

# Verify backup
if [ -f "${BACKUP_FILE}" ]; then
    FILESIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "Backup completed successfully: ${BACKUP_FILE} (${FILESIZE})"
else
    echo "ERROR: Backup file not created!"
    exit 1
fi

# Clean up old backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name "diligence_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

# List remaining backups
echo "Current backups:"
ls -lh "${BACKUP_DIR}"

echo "Backup process completed at $(date)"
