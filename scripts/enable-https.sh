#!/usr/bin/env bash
set -euo pipefail
domain="${1:?Domain required}"
email="${2:-}"
[[ "$EUID" == 0 ]] || { echo 'Root required.'; exit 1; }
[[ "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$ && "$domain" != *..* ]] || { echo 'Invalid domain.'; exit 1; }
# A certificate already provisioned by the existing deployment stays intact.
if [[ -f "/etc/letsencrypt/live/$domain/fullchain.pem" ]]; then
 echo "Existing certificate preserved for $domain. Certbot renewal remains configured."
 exit 0
fi
python3 - "$domain" <<'PY'
import socket,sys
try:socket.getaddrinfo(sys.argv[1],80,type=socket.SOCK_STREAM)
except socket.gaierror:raise SystemExit('Domain DNS is not ready. Point its A record to this VPS, open inbound TCP 80/443 in the cloud firewall, then run: bash scripts/enable-https.sh '+sys.argv[1])
PY
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
