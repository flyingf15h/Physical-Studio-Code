#!/bin/sh
# Nightly backup of the designs volume: accounts, sessions, saved projects, BOM parts, every build with
# its photos and commits, and step reports. Ready-made guides are left out (they're in the repo).
# Keeps the last $KEEP_DAYS days in $BACKUP_DIR. Run it on the server as root:
#
#   sh /opt/Physical-Studio-Code/deploy/backup.sh           # back up now
#   sh /opt/Physical-Studio-Code/deploy/backup.sh install   # and every night at 04:17 (cron)
#
# Restore: docker compose stop mcp viewer, then
#   tar xzf <backup> -C /var/lib/docker/volumes/physical-studio_designs/_data && docker compose start mcp viewer
set -eu
cd "$(dirname "$0")/.."
REPO=$(pwd)
BACKUP_DIR=${BACKUP_DIR:-/var/backups/physical-studio}
KEEP_DAYS=${KEEP_DAYS:-7}

if [ "${1:-}" = install ]; then
  line="17 4 * * * sh $REPO/deploy/backup.sh >> /var/log/physical-studio-backup.log 2>&1"
  { crontab -l 2>/dev/null | grep -v 'deploy/backup.sh' || true; echo "$line"; } | crontab -  # || true: no crontab yet
  crontab -l | grep -q 'deploy/backup.sh' && echo "installed: $line"
fi

DATA=$(docker volume inspect -f '{{.Mountpoint}}' physical-studio_designs)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"  # it holds password hashes and people's photos
excludes=""
for d in mcp-server/physical_studio/bench/ready/*/; do
  excludes="$excludes --exclude=./build-$(basename "$d")"
done
out="$BACKUP_DIR/designs-$(date -u +%Y%m%d-%H%M).tar.gz"
# shellcheck disable=SC2086
tar czf "$out.tmp" -C "$DATA" $excludes --exclude='*.tmp' .
mv "$out.tmp" "$out"
find "$BACKUP_DIR" -name 'designs-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) backed up to $out ($(du -h "$out" | cut -f1))"
