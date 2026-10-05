#!/usr/bin/env bash
set -euo pipefail
kit="$(cd "$(dirname "$0")" && pwd)"
target="${1:-/root/gems-pos}"
cd "$target"
[[ -f compose.yml && -d addons/gems_pos ]] || { echo 'Existing Gems deployment required.'; exit 1; }
# Keep existing HTTPS/maintenance service and compose configuration.
bash scripts/backup.sh "$target"
exec 9>.maintenance.lock
flock -n 9 || { echo 'Another maintenance task is running.'; exit 1; }
docker compose stop odoo
cp -a "$kit/addons/gems_pos/." addons/gems_pos/
find addons -type d -exec chmod 755 {} +
find addons -type f -exec chmod 644 {} +
docker compose run --rm odoo odoo -d gemspos -u gems_pos --stop-after-init --no-http
docker compose up -d odoo
echo 'Updated. Open Reports & profit and press Ctrl+Shift+R.'
