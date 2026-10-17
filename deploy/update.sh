#!/bin/sh
# Pull the latest code and rebuild everything on the Vultr box. Run it on the server, as root
# (SSH, or Vultr's web console: Products -> the instance -> View Console):
#
#   sh /opt/Physical-Studio-Code/deploy/update.sh [domains]
#
# domains (optional) replaces DOMAIN in deploy/.env, e.g.
#   sh deploy/update.sh "physicalstudio.work, www.physicalstudio.work, 155-138-154-8.sslip.io"
# Caddy serves every name in the list and gets a certificate for each once its DNS points here.
set -eu
cd "$(dirname "$0")/.."
git pull --ff-only
cd deploy
if [ $# -gt 0 ]; then
  if grep -q '^DOMAIN=' .env; then sed -i "s|^DOMAIN=.*|DOMAIN=$1|" .env; else echo "DOMAIN=$1" >> .env; fi
fi
grep -qE "^GEMINI_API_KEYS?=." .env || echo "warning: GEMINI_API_KEY and GEMINI_API_KEYS are both empty in deploy/.env"
for key in OPENAI_API_KEY DEEPSEEK_API_KEY; do
  grep -q "^$key=." .env || echo "warning: $key is empty in deploy/.env"
done
docker compose up -d --build
docker compose ps
echo
grep '^DOMAIN=' .env
echo "Certificates for new names can take a minute; watch with: docker compose logs -f caddy"
