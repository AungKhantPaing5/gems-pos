# Gems POS — Odoo 19 Community

Gem shop POS with admin/staff pages, per-account permissions, product photos, unified item codes/barcodes, stock corrections, sales vouchers, payment methods, multi-user stock locking, selected Stock In barcode labels with Myanmar fonts, administrator Backup/Restore, monthly/yearly stock and profit reports, Excel export and browser Save as PDF. See [FEATURES.md](FEATURES.md) for report semantics.

## Ubuntu 24.04 VPS: one command

```bash
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/bootstrap.sh | bash'
```

Run as root. Open **http://YOUR_VPS_IP** after installation; `/` redirects to `/gems`. The installer detects the public IPv4 automatically. No domain, DNS record or certificate is required. Allow inbound TCP **80** in the Vultr/cloud firewall and keep your SSH access allowed. If automatic IP detection fails, append `--ip YOUR_VPS_IP` after `bash -s --` in the command above.

Existing `/root/gems-pos` is detected automatically: take a backup, update the addon and add an HTTP IP site. Accounts, secrets, Compose, maintenance configuration, scheduled backups and shop data are retained. This mode never creates a second database or resets accounts. Existing domain/TLS sites are left in place.

On an empty Ubuntu 24.04 VPS the installer configures official Docker Engine/Compose, PostgreSQL 16, Odoo 19, Nginx, the maintenance service and a daily full local backup. Initial website accounts are `admin/admin` and `user/user`; change them after signing in. Database password and maintenance signing key are generated per server.

Only Nginx is publicly exposed; Odoo and maintenance listen on loopback ports 8070 and 8099. If those ports belong to another application, installation stops before database initialization. The HTTP site matches the VPS IPv4 explicitly without replacing unrelated Nginx sites. Failed Nginx validation restores the previous IP-site configuration. Fresh installs require Ubuntu 24.04 with systemd; existing Docker runtime packages are not replaced.

## Optional domain and HTTPS

Keep the one-command installer above for HTTP IP access. For DNS records, a separate HTTPS command, existing-domain-site handling and automatic certificate renewal checks, follow **[HTTPS.md](HTTPS.md)**. The optional helper accepts your chosen domain; no domain is hardcoded in the installer.

## Existing WSL deployment

Do not install another full project. Update the existing project path:

```bash
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/bootstrap.sh | bash -s -- --update --target /root/gems-pos-wsl-v12'
```

Docker Desktop must be running with this Ubuntu's WSL integration enabled. Existing Nginx/maintenance processes remain in place; Windows browser URL is http://localhost:8080/gems. Fresh WSL setup uses the separately provided WSL full ZIP rather than the cloud initializer.

## Repeatable/pinned deployments

Set `GEMS_REF` to a Git commit SHA in the bootstrap environment to download that exact source archive, and download bootstrap.sh from the same SHA instead of main. `GEMS_REPOSITORY` optionally selects another public `owner/repo`. Repository sources are downloaded into a temporary directory, checked, then the deployment runs; failed downloads cannot silently launch an empty installer.

## Backups

Fresh cloud installations have a full daily local backup at 03:00–03:10 Myanmar time. Data, image filestore, addon and environment are included. Archives are in the project `backups/` directory and not committed to GitHub. Local backups are retained; manage available disk space. Existing configured offsite timers are not replaced. The `ops/` kit supports Vultr Object Storage using rclone; it needs that bucket's credentials and remote configuration. Credentials are entered on the server, not put in this repository. Manual Backup/Restore is also available to the full administrator.

## Reports and permissions

Full administrators can manage website users and their View/Add/Edit/Delete/Stock/Barcode/Sales rights. Delegated Managers do not receive administrator/report/backup access. Reports use Myanmar-time calendar months/years. Cost price is captured on sale lines; older sales without a cost produce "Cost missing", not a guessed profit. Net profit is revenue after discount minus captured cost of sold goods minus recorded operating expenses. PDF export uses the browser Save as PDF dialog. Excel exports actual `.xlsx` files without additional Odoo dependencies.

## Source and checks

No database dumps, server environment, uploaded photos, customer records, tokens or server-specific passwords are included. `.gitignore` excludes these. Bundled Noto Sans Myanmar includes its license. Module license is LGPL-3; Docker/Odoo/PostgreSQL/fonts keep their own licenses.

Offline tests cover report math and date boundaries, Excel readback, authorization, cost snapshots, stock cancellation and correction, permissions, barcode decoding, selection/printing and scanner behavior. `tests/check_deploy.py` uses mocked Docker/system commands to test install/update selection, existing-data preservation, invalid targets and bootstrap network failure. `tests/check_ip_access.py` checks IP detection, proxy routing, configuration ownership and rollback. Full Docker/systemd/Nginx integration must be checked on the actual VPS.
