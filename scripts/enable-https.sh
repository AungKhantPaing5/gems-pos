#!/usr/bin/env bash
set -euo pipefail
domain="${1:?Domain required}"
email="${2:-}"
[[ "$EUID" == 0 ]] || { echo 'Root required.'; exit 1; }
kit="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$kit/configure-domain.py" ]] || { echo 'Missing configure-domain.py; download both HTTPS helper files.'; exit 1; }
domain="$(python3 - "$kit/configure-domain.py" "$domain" <<'PYDOMAIN'
import importlib.util,sys
spec=importlib.util.spec_from_file_location('gems_domain',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:print(m.valid_domain(sys.argv[2]))
except ValueError as exc:raise SystemExit(str(exc))
PYDOMAIN
)"
python3 - "$domain" <<'PY'
import socket,sys
try:socket.getaddrinfo(sys.argv[1],80,type=socket.SOCK_STREAM)
except socket.gaierror:raise SystemExit('Domain DNS is not ready. Point its A record to this VPS, open inbound TCP 80/443 in the cloud firewall, then run: bash scripts/enable-https.sh '+sys.argv[1])
PY
command -v nginx >/dev/null || { echo 'Install Gems POS first; Nginx is required.'; exit 1; }
python3 "$kit/configure-domain.py" "$domain"
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
 ufw allow 80/tcp
 ufw allow 443/tcp
fi
if command -v certbot >/dev/null; then
 certbot_cmd="$(command -v certbot)"
elif [[ -x /snap/bin/certbot ]]; then
 certbot_cmd=/snap/bin/certbot
else
 apt-get update
 apt-get install -y snapd
 systemctl enable --now snapd.socket
 snap install --classic certbot
 certbot_cmd=/snap/bin/certbot
fi
args=(--nginx -d "$domain" --redirect --non-interactive --agree-tos)
if [[ -n "$email" ]]; then args+=(--email "$email"); else args+=(--register-unsafely-without-email); fi
if ! "$certbot_cmd" "${args[@]}"; then
 echo 'The shop was installed successfully; HTTPS issuance failed.'
 echo "Check domain A/AAAA records and inbound TCP 80/443, then retry: bash scripts/enable-https.sh $domain"
 exit 1
fi
nginx -t
systemctl reload nginx
echo "Ready: https://$domain/gems"
echo "Check automatic renewal: $certbot_cmd renew --dry-run"
