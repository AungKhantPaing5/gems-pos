# Vultr Ubuntu 24.04 — Gems POS daily backups and HTTP IP access

This operations kit configures a verified daily application backup, keeps 14 days on the VPS and sends a private copy to Vultr Object Storage with a 30-day remote retention. It expects the existing cloud project at `/root/gems-pos` and its tested `scripts/backup.sh`. It does not alter DNS, Nginx/HTTPS, Odoo compose, credentials, or POS data. Run the current v13 addon update first if it has not been deployed yet.

## 1. Check HTTP IP access

The GitHub installer detects the VPS public IPv4 and adds HTTP access. Open `http://YOUR_VPS_IP`; the root redirects to `/gems`. Allow TCP 80 in Vultr Firewall and keep SSH allowed. No DNS or certificate setup is required.

Run on the VPS:

```bash
nginx -t
curl -I http://127.0.0.1/gems
curl -I http://127.0.0.1:8070/gems
```

Odoo stays bound to `127.0.0.1:8070`; `/gems-maintenance/` proxies to `127.0.0.1:8099`. If external access times out while local checks work, check the cloud firewall and the instance's public IPv4. This backup kit does not change web access configuration.

## 2. Create remote backup storage

In the Vultr Console create a **private** Object Storage bucket. Singapore endpoint is `https://sgp1.vultrobjects.com`; select the endpoint matching the bucket's region. Create/copy its Access Key and Secret Key. Never paste these credentials into chat, the POS, GitHub or shell commands.

On the VPS as root, run `rclone config`. Make a remote named `vultr`, storage type `s3`, provider `Vultr`, `env_auth=false`, enter the Object Storage keys, leave region and location constraint blank, set endpoint to `https://sgp1.vultrobjects.com` for a Singapore bucket, and set ACL `private`. Save. The rclone config is kept in root's private config folder. For another bucket region, use its own endpoint hostname (Vultr lists `ams1`, `ewr1`, `sjc1`, `sgp1`).

## 3. Install the daily backup timer

Copy `gems-pos-vultr-ops.zip` to `/root` on the VPS, then:

```
cd /root
unzip -o gems-pos-vultr-ops.zip -d /root/
cd /root/gems-pos-vultr-ops
bash install-auto-backup.sh /root/gems-pos
```

When prompted, enter a private remote folder such as `vultr:gems-pos-backups`. The installer checks that it can create and remove a temporary test object, writes a root-only config, enables a daily 03:00 Myanmar-time systemd timer and runs the first backup immediately. The application backup contains PostgreSQL, product photos/filestore, addon and deployment config; it briefly stops Odoo while the consistent database/filestore copies are taken, then starts it again. The offsite object is checked for matching size before success. Local archives older than 14 days are removed only after a verified remote copy exists. Remote Gems archives older than 30 days are removed from this dedicated prefix.

Verify:

```
systemctl list-timers gems-pos-auto-backup.timer
systemctl status gems-pos-auto-backup.service
journalctl -u gems-pos-auto-backup.service -n 60 --no-pager
rclone lsl vultr:gems-pos-backups
curl -I http://127.0.0.1/gems
```

If the first run failed, use the `journalctl` output to fix the reported issue, then retry with `systemctl start gems-pos-auto-backup.service`.

## 4. Vultr instance backup

Separately, Vultr Console → Products → Compute → select the instance → Backups → enable Automatic Backups → choose Daily and schedule. This option costs an additional 20% of the instance price. Use it as a whole-server recovery layer; Vultr reports keeping only the two most recent automatic backups, and they are point-in-time disk images. The scheduled POS backup above provides individual application archives and 30 days of object storage history. Restores of app archives are available from POS Admin → Backup & Restore; the CLI restore is `bash /root/gems-pos/scripts/restore-ui.sh /path/to/backup.tar.gz /root/gems-pos --replace-existing` (it takes a pre-restore backup).

Before relying on the schedule, download a copy of the first archive and do a test restore on a separate empty staging database/server. Never use `docker compose down -v`; it deletes the live database volume.

## Checks performed

Shell syntax and systemd timer expression checked locally. The live Vultr account, DNS records, Object Storage credentials/bucket, SSH firewall, Nginx and certificate cannot be changed or verified from this workspace. Test the first completed upload and check the public URL from a browser.
