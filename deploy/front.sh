#!/bin/sh
# Choose what https://physicalstudio.work shows, on the Vultr box, as root:
#
#   sh /opt/Physical-Studio-Code/deploy/front.sh builder   # Circuit Studio's Build helper
#   sh /opt/Physical-Studio-Code/deploy/front.sh classic   # the viewer app (screen 1 -> design -> guide)
#
# Either way the viewer app stays at https://classic.physicalstudio.work and Circuit Studio at
# /studio/. It only moves host names between DOMAIN (viewer app, deploy/Caddyfile) and
# STUDIO_DOMAIN (Build helper, deploy/Caddyfile.local) in deploy/.env and restarts Caddy, so
# switching back is the same command with the other word.
set -eu
cd "$(dirname "$0")"
MAIN="physicalstudio.work, www.physicalstudio.work"
case "${1:-}" in
  builder)
    domain="classic.physicalstudio.work, 155-138-154-8.sslip.io"
    studio="$MAIN, studio.155-138-154-8.sslip.io" ;;
  classic)
    domain="$MAIN, classic.physicalstudio.work, 155-138-154-8.sslip.io"
    studio="studio.155-138-154-8.sslip.io" ;;
  *) echo "usage: sh deploy/front.sh builder|classic"; exit 2 ;;
esac
cp .env ".env.bak-$(date +%s)"
for kv in "DOMAIN=$domain" "STUDIO_DOMAIN=$studio"; do
  k=${kv%%=*}
  if grep -q "^$k=" .env; then sed -i "s|^$k=.*|$kv|" .env; else echo "$kv" >> .env; fi
done
docker compose up -d caddy mcp
grep -E '^(DOMAIN|STUDIO_DOMAIN)=' .env
echo "physicalstudio.work now shows: $1 (certificates for moved names can take a minute)"
