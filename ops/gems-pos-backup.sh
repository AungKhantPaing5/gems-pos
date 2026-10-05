#!/usr/bin/env bash
set -euo pipefail
source /etc/gems-pos-backup.conf
exec 9>/run/lock/gems-pos-auto-backup.lock
flock -n 9 || { echo 'Another scheduled backup is already running.'; exit 0; }
cd "$GEMS_POS_ROOT"
[[ "$GEMS_POS_REMOTE" =~ ^vultr:[A-Za-z0-9._/-]+$ ]] || { echo 'Invalid backup destination.'; exit 1; }
mkdir -p backups
# The application backup safely stops Odoo, dumps PostgreSQL, copies its image filestore/addon/config, verifies the archive, then restarts Odoo.
bash scripts/backup.sh "$GEMS_POS_ROOT"
archive="$(find backups -maxdepth 1 -type f -name 'gemspos-*.tar.gz' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
[[ -n "$archive" && -s "$archive" ]]
remote_file="${GEMS_POS_REMOTE%/}/$(basename "$archive")"
rclone copyto "$archive" "$remote_file" --retries 3 --low-level-retries 10
# Confirm the remote object's byte size before allowing local retention or declaring success.
rclone lsjson --stat "$remote_file" | python3 -c 'import json,os,sys; d=json.load(sys.stdin); expected=os.path.getsize(sys.argv[1]); actual=d.get("Size"); sys.exit(0 if actual==expected else 1)' "$archive"
echo "Verified offsite archive: $remote_file ($(stat -c %s "$archive") bytes)"
# Retain older local archives only when the matching remote copy exists with the same size.
while IFS= read -r -d '' old; do
  remote_old="${GEMS_POS_REMOTE%/}/$(basename "$old")"
  if rclone lsjson --stat "$remote_old" 2>/dev/null | python3 -c 'import json,os,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("Size")==os.path.getsize(sys.argv[1]) else 1)' "$old"; then
    rm -f -- "$old"
  else
    echo "Keeping local archive; no verified offsite copy: $old"
  fi
done < <(find backups -maxdepth 1 -type f -name 'gemspos-*.tar.gz' -mtime "+${LOCAL_RETENTION_DAYS}" -print0)
# S3 endpoint stores files privately; delete only matching, expired Gems archives in this configured prefix.
rclone delete "$GEMS_POS_REMOTE" --min-age "${REMOTE_RETENTION_DAYS}d" --include '/gemspos-*.tar.gz' --retries 3
echo "Gems POS backup succeeded: $(basename "$archive")"
