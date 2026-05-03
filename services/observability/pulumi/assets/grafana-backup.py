import json
import logging
import os
import shutil
import sqlite3

from datetime import UTC, datetime
from pathlib import Path

source_db = Path('/source/grafana/grafana.db')
backup_dir = Path('/backup/grafana')
secrets_dir = backup_dir / 'secrets'
local_backup_db = Path('/tmp/grafana.db')
backup_db_tmp = backup_dir / 'grafana.db.tmp'
backup_db = backup_dir / 'grafana.db'
manifest_tmp = backup_dir / 'manifest.json.tmp'
manifest = backup_dir / 'manifest.json'
secret_source = Path('/source/secrets/secret-key')
secret_target = secrets_dir / 'grafana-secret-key.secret-key'

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO,
)
log = logging.getLogger('grafana-backup')


def size_bytes(path: Path) -> int:
    return path.stat().st_size


log.info('Starting Grafana backup')
log.info('Source database: %s', source_db)
log.info('Backup directory: %s', backup_dir)
log.info('Secret source: %s', secret_source)

if not source_db.exists():
    raise FileNotFoundError(f'Missing Grafana database: {source_db}')

backup_dir.mkdir(parents=True, exist_ok=True)
secrets_dir.mkdir(parents=True, exist_ok=True)
log.info('Ensured backup directories exist: %s, %s', backup_dir, secrets_dir)

if backup_db_tmp.exists():
    log.info('Removing stale temporary backup file: %s', backup_db_tmp)
    backup_db_tmp.unlink()
if local_backup_db.exists():
    log.info('Removing stale local SQLite backup file: %s', local_backup_db)
    local_backup_db.unlink()

log.info('Creating consistent SQLite backup in local container storage: %s', local_backup_db)
source = sqlite3.connect(f'file:{source_db}?mode=ro', timeout=30, uri=True)
target = sqlite3.connect(local_backup_db)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
log.info('Created local SQLite backup: %s bytes', size_bytes(local_backup_db))

log.info('Copying SQLite backup to Samba temporary file: %s', backup_db_tmp)
shutil.copyfile(local_backup_db, backup_db_tmp)
os.replace(backup_db_tmp, backup_db)
log.info('Replaced Samba SQLite backup: %s (%s bytes)', backup_db, size_bytes(backup_db))

log.info('Copying Grafana secret key to backup target: %s', secret_target)
shutil.copyfile(secret_source, secret_target)
secret_target.chmod(0o600)
log.info('Copied Grafana secret key backup: %s bytes', size_bytes(secret_target))

manifest_data = {
    'created_at': datetime.now(UTC).isoformat(),
    'source_pvc': 'grafana-data',
    'secret_locator': 'k8s://Secret/observability/grafana-secret-key#secret-key',
    'files': [
        '/backup/grafana/grafana.db',
        '/backup/grafana/secrets/grafana-secret-key.secret-key',
        '/backup/grafana/manifest.json',
    ],
}

log.info('Writing backup manifest: %s', manifest)
manifest_tmp.write_text(json.dumps(manifest_data, indent=2) + '\n', encoding='utf-8')
os.replace(manifest_tmp, manifest)
log.info('Wrote backup manifest: %s bytes', size_bytes(manifest))
log.info('Grafana backup completed successfully')
