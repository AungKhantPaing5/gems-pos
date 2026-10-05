#!/usr/bin/env bash
# Public GitHub entrypoint. Source is downloaded before any application changes.
set -euo pipefail
[[ "$EUID" == 0 ]] || { echo 'Run this installer as root or with sudo.'; exit 1; }
repo="${GEMS_REPOSITORY:-AungKhantPaing5/gems-pos}"
ref="${GEMS_REF:-main}"
[[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ && "$ref" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo 'Invalid repository/ref.'; exit 1; }
command -v curl >/dev/null || { apt-get update; apt-get install -y ca-certificates curl; }
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
curl --fail --show-error --silent --location --retry 3 --connect-timeout 20 \
  "https://api.github.com/repos/$repo/tarball/$ref" -o "$work/source.tar.gz"
mkdir "$work/source"
tar -xzf "$work/source.tar.gz" -C "$work/source" --strip-components=1
[[ -f "$work/source/deploy.sh" && -f "$work/source/addons/gems_pos/__manifest__.py" ]] || { echo 'Incomplete source archive.'; exit 1; }
bash "$work/source/deploy.sh" "$@"
