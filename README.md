# Gems POS — Odoo 19 Community

Gem shop POS with admin/staff pages, per-account permissions, product photos, unified item codes/barcodes, stock corrections, sales vouchers, payment methods, multi-user stock locking, selected Stock In barcode labels with Myanmar fonts, administrator Backup/Restore, monthly/yearly stock and profit reports, Excel export and browser Save as PDF. See [FEATURES.md](FEATURES.md) for report semantics.

## Ubuntu 24.04 VPS: one command

```bash
bash -o pipefail -c 'curl -fsSL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/bootstrap.sh | bash -s -- --domain payapi.uk'
```

Run as root. Existing `/root/gems-pos` is detected automatically: back up and update the addon, retain Compose, HTTPS, accounts, secrets, maintenance configuration, scheduled backups and shop data. This mode never creates a second database or resets accounts.

On an empty VPS the installer configures official Docker Engine/Compose, PostgreSQL 16, Odoo 19, Nginx, the maintenance service, a daily full local backup and HTTPS. Initial website accounts are `admin/admin` and `user/user`, matching the existing project defaults. Database password and maintenance signing key are generated per server. Optional certificate email: append `--email you@example.com`.

Before a fresh deployment, point the domain A record to the VPS, remove incorrect AAAA records, and permit TCP 80 and 443 in your cloud firewall. DNS/ACME failure leaves the initialized shop intact; retry `bash /root/gems-pos/scripts/enable-https.sh payapi.uk` after fixing DNS/firewall. It does not reset accounts or reinstall the database. An existing shop's HTTPS is preserved.

The root domain redirects to `/gems`. Only Nginx is publicly exposed; Odoo and maintenance listen on loopback ports 8070 and 8099. If those ports belong to another application, installation stops before database initialization. It never stops arbitrary containers or changes unrelated Nginx sites. Fresh installs require Ubuntu 24.04 with systemd; it does not replace existing Docker runtime packages.

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

Offline tests cover report math and date boundaries, Excel readback, authorization, cost snapshots, stock cancellation and correction, permissions, barcode decoding, selection/printing and scanner behavior. `tests/check_deploy.py` uses mocked Docker/system commands to test install/update selection, existing-data preservation, invalid targets and bootstrap network failure. Full Docker/systemd/ACME integration must be checked on the actual VPS.
