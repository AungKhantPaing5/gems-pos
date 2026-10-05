#!/usr/bin/env bash
set -euo pipefail
umask 077
target="${1:-/root/gems-pos}"
cd "$target"
if [[ "${GEMS_LOCK_HELD:-0}" != 1 ]]; then
  exec 9>.maintenance.lock
  flock -n 9 || { echo 'Another maintenance task is running.'; exit 1; }
fi
mkdir -p backups
work="$(mktemp -d "$PWD/backups/.work-XXXXXX")"
was_running="$(docker compose ps --status running --services odoo)"
cleanup() {
  rm -rf "$work"
  if [[ -n "$was_running" ]]; then docker compose up -d odoo >/dev/null; fi
}
trap cleanup EXIT
docker compose stop odoo >/dev/null
docker compose exec -T db pg_dump -U odoo -d gemspos -Fc > "$work/database.dump"
docker compose run --rm --no-deps -T --entrypoint bash odoo -c \
  'mkdir -p /var/lib/odoo/filestore/gemspos; tar -C /var/lib/odoo -czf - filestore/gemspos' > "$work/filestore.tar.gz"
cp -a addons "$work/addons"
cp compose.yml "$work/compose.yml"
[[ ! -f .env ]] || cp .env "$work/environment.env"
printf 'GEMS_BACKUP_V1\nDatabase=gemspos\nPostgreSQL=16\nOdoo=19\n' > "$work/manifest.txt"
(cd "$work"; sha256sum database.dump filestore.tar.gz > SHA256SUMS)
archive="$PWD/backups/gemspos-$(date +%Y%m%d-%H%M%S)-$$.tar.gz"
tar -C "$work" -czf "$archive" .
tar -tzf "$archive" >/dev/null
echo "$archive"
