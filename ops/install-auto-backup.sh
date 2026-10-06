#!/usr/bin/env bash
set -euo pipefail
[[ "$EUID" == 0 ]] || { echo 'Run with sudo/root.'; exit 1; }
target="${1:-/root/gems-pos}"
[[ -d "$target" && -f "$target/compose.yml" && -f "$target/scripts/backup.sh" ]] || { echo "Existing Gems POS deployment with scripts/backup.sh required: $target"; exit 1; }
command -v systemctl >/dev/null && systemctl is-system-running --quiet || { echo 'Ubuntu systemd must be running.'; exit 1; }
command -v rclone >/dev/null || { apt-get update; apt-get install -y rclone; }
if ! rclone listremotes | grep -Fxq 'vultr:'; then
  echo 'First create a private Vultr Object Storage bucket, then run: rclone config'
  echo 'Create remote name vultr, storage type s3, provider Other, and enter the Object Storage access/secret keys and regional endpoint shown in Vultr.'
  echo 'Exit rclone config, then run this installer again.'
  exit 2
fi
read -r -p 'Vultr remote folder (example: vultr:gems-pos-backups): ' destination
[[ "$destination" =~ ^vultr:[A-Za-z0-9._/-]+$ ]] || { echo 'Use a bucket/path without spaces or quotes.'; exit 1; }
rclone mkdir "$destination"
testfile="${destination%/}/.gems-pos-backup-write-test"
rclone touch "$testfile"
rclone deletefile "$testfile"
cat > /etc/gems-pos-backup.conf <<EOF
GEMS_POS_ROOT='$target'
GEMS_POS_REMOTE='$destination'
LOCAL_RETENTION_DAYS=14
REMOTE_RETENTION_DAYS=30
EOF
chmod 600 /etc/gems-pos-backup.conf
install -m 750 gems-pos-backup.sh /usr/local/sbin/gems-pos-backup
cat > /etc/systemd/system/gems-pos-auto-backup.service <<'EOF'
[Unit]
Description=Create and upload a full Gems POS backup
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/gems-pos-backup
TimeoutStartSec=0
UMask=0077
EOF
cat > /etc/systemd/system/gems-pos-auto-backup.timer <<'EOF'
[Unit]
Description=Daily Gems POS backup at 03:00 Myanmar time
[Timer]
OnCalendar=*-*-* 20:30:00 UTC
RandomizedDelaySec=10m
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now gems-pos-auto-backup.timer
systemctl start gems-pos-auto-backup.service
echo 'Daily backup configured. Verify with: systemctl status gems-pos-auto-backup.service; journalctl -u gems-pos-auto-backup.service -n 50'
