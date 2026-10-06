#!/usr/bin/env bash
set -euo pipefail
umask 077
kit="$(cd "$(dirname "$0")" && pwd)"
target=/root/gems-pos
vps_ip=''
mode=auto
while (($#)); do
 case "$1" in
  --target) target="${2:?Missing target}"; shift 2;;
  --ip) vps_ip="${2:?Missing VPS IPv4}"; shift 2;;
  --install) mode=install; shift;;
  --update) mode=update; shift;;
  --help) echo 'Usage: deploy.sh [--target /root/gems-pos] [--ip YOUR_VPS_IP] [--install|--update]'; exit 0;;
  *) echo "Unknown argument: $1"; exit 1;;
 esac
done
[[ "$EUID" == 0 ]] || { echo 'Root/sudo required.'; exit 1; }
[[ "$target" =~ ^/[A-Za-z0-9._/-]+$ && "$target" != / && "$target" != /root && "$target" != /home && "$target" != /opt ]] || { echo 'Use an absolute application folder without spaces.'; exit 1; }
if [[ -n "$vps_ip" ]]; then
 python3 - "$vps_ip" <<'PYCODE'
import ipaddress,sys
try:
 ip=ipaddress.IPv4Address(sys.argv[1])
 if ip.is_unspecified or ip.is_multicast or ip.is_loopback:raise ValueError()
except ValueError:raise SystemExit('Valid VPS IPv4 required.')
PYCODE
fi
ip_args=()
[[ -z "$vps_ip" ]] || ip_args=(--ip "$vps_ip")
# Prevent two deploys. Root-controlled lock rather than the downloaded temp folder.
mkdir -p /run/lock
exec 8>/run/lock/gems-pos-deploy.lock
flock -n 8 || { echo 'Another Gems deployment is running.'; exit 1; }
if [[ -f "$target/compose.yml" && -d "$target/addons/gems_pos" && ! -f "$target/.installing" ]]; then
 [[ "$mode" != install ]] || { echo 'Existing project found. Run in auto/update mode.'; exit 1; }
 command -v docker >/dev/null && docker compose version >/dev/null || { echo 'Docker Compose must be available for the existing deployment.'; exit 1; }
 [[ -f "$target/scripts/backup.sh" ]] || { echo 'Existing project lacks scripts/backup.sh; no files were replaced.'; exit 1; }
 echo "Existing Gems POS detected: $target. Taking a backup and updating to v13."
 bash "$kit/apply-update.sh" "$target"
 if [[ "$(uname -r)" == *[Mm]icrosoft* ]]; then
  echo 'WSL update complete. Open http://localhost:8080/gems and press Ctrl+Shift+R.'
 else
  command -v nginx >/dev/null || { apt-get update; apt-get install -y nginx; }
  install -m 755 "$kit/scripts/configure-ip-access.py" "$target/scripts/configure-ip-access.py"
  python3 "$target/scripts/configure-ip-access.py" "$target" "${ip_args[@]}"
  echo 'Press Ctrl+Shift+R. Existing accounts and data were preserved.'
 fi
 exit 0
fi
[[ "$mode" != update ]] || { echo 'No existing Gems POS at the target path.'; exit 1; }
if [[ -e "$target" && ! -f "$target/.installing" ]] && [[ -n "$(ls -A "$target")" ]]; then
 echo 'Target folder is not empty and is not a recognized Gems installation. No files replaced.'; exit 1
fi
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Fresh cloud installer supports Ubuntu 24.04. Existing deployments can use --update.'; exit 1; }
if [[ "$(uname -r)" == *[Mm]icrosoft* ]]; then echo 'Use the WSL full package for a new local test; this fresh installer configures cloud systemd/HTTP IP access.'; exit 1; fi
apt-get update
apt-get install -y ca-certificates curl python3 util-linux iproute2 nginx
if ! command -v docker >/dev/null; then
 # Do not replace an unrelated existing container runtime.
 for pkg in docker.io podman-docker containerd runc; do
  if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed'; then
   echo "Existing runtime package $pkg detected. Configure Docker Compose first; no runtime removed."; exit 1
  fi
 done
 install -m 0755 -d /etc/apt/keyrings
 curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
 chmod a+r /etc/apt/keyrings/docker.asc
 arch="$(dpkg --print-architecture)"
 cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
 apt-get update
 apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version >/dev/null || { echo 'Install the Docker Compose plugin for your existing Docker installation.'; exit 1; }
systemctl enable --now docker
# Check required service ports before database initialization.
python3 - <<'PY'
import socket
for port in (8070,8099):
 s=socket.socket()
 try:s.bind(('127.0.0.1',port))
 except OSError:raise SystemExit(f'Port {port} is occupied. Update the existing shop with --target rather than creating another shop.')
 finally:s.close()
PY
mkdir -p "$target"
# Allows retry of a partially initialized project without resetting existing data.
touch "$target/.installing"
for dir in addons scripts maintenance; do
 mkdir -p "$target/$dir"
 cp -a "$kit/$dir/." "$target/$dir/"
done
cp "$kit/compose.yml" "$kit/setup-users.py" "$target/"
chmod 755 "$target/maintenance"
cd "$target"
if [[ ! -f .env ]]; then
 python3 - <<'PY'
from pathlib import Path
import secrets,os
p=Path('.env');p.write_text('DB_PASSWORD='+secrets.token_hex(24)+'\n');os.chmod(p,0o600)
PY
fi
if [[ ! -f maintenance/key ]]; then
 python3 - <<'PY'
from pathlib import Path
import secrets
Path('maintenance/key').write_bytes(secrets.token_bytes(32))
PY
fi
chmod 444 maintenance/key
find addons -type d -exec chmod 755 {} +
find addons -type f -exec chmod 644 {} +
docker compose up -d --wait db
exists="$(docker compose exec -T db psql -U odoo -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='gemspos'")"
if [[ "$exists" == 1 && ! -f .install-db-created ]]; then
 echo 'Existing database detected without an installer marker. No accounts were reset. Inspect the database and use update mode.'; exit 1
fi
if [[ "$exists" != 1 ]]; then
 docker compose exec -T db createdb -U odoo gemspos
 touch .install-db-created
fi
docker compose run --rm odoo odoo -d gemspos -i gems_pos --without-demo=all --stop-after-init --no-http
if [[ ! -f .install-users-done ]]; then
 docker compose run --rm -T odoo odoo shell -d gemspos --no-http < setup-users.py
 touch .install-users-done
fi
cat > /etc/systemd/system/gems-maintenance.service <<EOF
[Unit]
Description=Gems POS administrator maintenance
After=docker.service
Requires=docker.service
[Service]
WorkingDirectory=$target
Environment=GEMS_ROOT=$target
ExecStart=/usr/bin/python3 $target/maintenance/server.py
Restart=on-failure
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now gems-maintenance
systemctl restart gems-maintenance
docker compose up -d odoo
# Daily local backup; existing offsite schedules are left as configured.
if [[ ! -e /etc/systemd/system/gems-pos-auto-backup.timer ]]; then
 cat > /etc/systemd/system/gems-pos-local-backup.service <<EOF
[Unit]
Description=Gems POS full daily local backup
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=$target
ExecStart=/usr/bin/bash $target/scripts/backup.sh $target
UMask=0077
TimeoutStartSec=0
EOF
 cat > /etc/systemd/system/gems-pos-local-backup.timer <<'EOF'
[Unit]
Description=Daily Gems backup at 03:00 Myanmar time
[Timer]
OnCalendar=*-*-* 20:30:00 UTC
RandomizedDelaySec=10m
Persistent=true
[Install]
WantedBy=timers.target
EOF
 systemctl daemon-reload
 systemctl enable --now gems-pos-local-backup.timer
fi
# Mark database initialization complete before configuring public IP access;
# a web configuration failure must not reset the database/accounts on retry.
touch .installed
rm -f .installing
python3 - <<'PY'
import urllib.request,time
for attempt in range(60):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8070/gems',timeout=2) as r:
   if r.status==200:break
 except Exception:time.sleep(2)
else:raise SystemExit('Odoo is still starting. Inspect: docker compose logs --tail=80 odoo')
PY
python3 "$target/scripts/configure-ip-access.py" "$target" "${ip_args[@]}"
echo 'Initial accounts: admin/admin and user/user.'
