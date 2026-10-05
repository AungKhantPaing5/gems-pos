#!/usr/bin/env bash
set -euo pipefail
umask 077
archive="$(realpath "${1:?Usage: restore.sh BACKUP TARGET --replace-existing}")"
target="${2:-/root/gems-pos}"
[[ "${3:-}" == --replace-existing ]] || { echo 'Restore overwrites current shop data. Add --replace-existing to proceed.'; exit 1; }
cd "$target"
exec 9>.maintenance.lock
flock -n 9 || { echo 'Another maintenance task is running.'; exit 1; }
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 - "$archive" "$work" <<'PY'
import tarfile,sys
with tarfile.open(sys.argv[1]) as t:
    t.extractall(sys.argv[2], filter='data')
PY
[[ "$(head -n 1 "$work/manifest.txt")" == GEMS_BACKUP_V1 ]] || { echo 'Unsupported backup format.'; exit 1; }
(cd "$work"; sha256sum -c SHA256SUMS)
python3 - "$work/filestore.tar.gz" <<'PYCODE'
import tarfile,sys
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1]) as t:
    for m in t.getmembers():
        p=PurePosixPath(m.name)
        if p.is_absolute() or '..' in p.parts or not (m.name=='filestore/gemspos' or m.name.startswith('filestore/gemspos/')) or not (m.isfile() or m.isdir()):
            raise SystemExit('Invalid filestore archive member')
PYCODE
[[ -d "$work/addons/gems_pos" ]] || { echo 'Module missing.'; exit 1; }
docker compose up -d --wait db
# Validate dump before touching the existing shop.
docker compose exec -T db pg_restore --list < "$work/database.dump" >/dev/null
exists="$(docker compose exec -T db psql -U odoo -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='gemspos'")"
if [[ "$exists" == 1 ]]; then
  echo 'Taking a full pre-restore backup...'
  GEMS_LOCK_HELD=1 bash scripts/backup.sh "$PWD"
else
  docker compose exec -T db createdb -U odoo -O odoo gemspos
fi
docker compose stop odoo
# A failed restore leaves Odoo stopped; do not serve a partially restored shop.
docker compose exec -T db pg_restore -U odoo -d gemspos --clean --if-exists --no-owner --exit-on-error --single-transaction < "$work/database.dump"
mkdir -p addons
cp -a "$work/addons/." addons/
stamp="$(date +%Y%m%d-%H%M%S)"
docker compose run --rm --no-deps -T --user root --entrypoint bash odoo -c \
  'if [ -d /var/lib/odoo/filestore/gemspos ]; then mv /var/lib/odoo/filestore/gemspos "/var/lib/odoo/filestore/gemspos.before-$1"; fi; tar -xzf - -C /var/lib/odoo; chown -R odoo:odoo /var/lib/odoo/filestore/gemspos' -- "$stamp" < "$work/filestore.tar.gz"
docker compose up -d odoo
echo 'Restored database, pictures and addons. Current compose/.env are preserved.'
