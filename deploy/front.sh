#!/bin/sh
# Choose what the front page of https://physicalstudio.work shows, on the Vultr box, as root:
#
#   sh /opt/Physical-Studio-Code/deploy/front.sh builder   # Circuit Studio's Build helper
#   sh /opt/Physical-Studio-Code/deploy/front.sh classic   # the viewer app's screen 1
#
# Only the bare root (/) changes: /guide, /api, /studio and the viewer app's assets keep working
# on physicalstudio.work either way, and https://classic.physicalstudio.work always shows the
# viewer app. It sets FRONT_HOSTS in deploy/.env (read by deploy/Caddyfile) and restarts Caddy,
# so switching back is the same command with the other word.
set -eu
cd "$(dirname "$0")"
case "${1:-}" in
  builder) hosts="physicalstudio.work www.physicalstudio.work" ;;
  classic) hosts="" ;;
  *) echo "usage: sh deploy/front.sh builder|classic"; exit 2 ;;
esac
cp .env ".env.bak-$(date +%s)"
grep -v '^FRONT_HOSTS=' .env > .env.new
if [ -n "$hosts" ]; then echo "FRONT_HOSTS=$hosts" >> .env.new; fi
mv .env.new .env
chmod 600 .env
docker compose up -d caddy
grep '^FRONT_HOSTS=' .env || echo "FRONT_HOSTS unset"
echo "physicalstudio.work/ now opens: $1"
