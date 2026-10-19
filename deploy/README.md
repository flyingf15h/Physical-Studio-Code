# Deploy (Vultr)

One server runs everything with Docker Compose:

| Service | What it does |
|---|---|
| `caddy` | HTTPS on 443 (Let's Encrypt certificate for `$DOMAIN`, renewed automatically). Required: browsers only allow camera/mic access on secure pages. `/mcp*` goes to the MCP server, everything else to the viewer. |
| `viewer` | The built React viewer, `POST /api/gemini-token` (single-use Gemini Live tokens for the voice; the key never reaches the browser), `POST /api/check-step` (the step checker: a camera frame against the step's check line, judged by `GEMINI_CHECK_MODEL`, or by DeepSeek's vision model when Gemini is rate limited), both rate limited per IP with optional `DEMO_CODE`, and `/out/<design>/` from the shared `designs` volume. |
| `mcp` | The MCP server over streamable HTTP at `https://$DOMAIN/mcp`, behind `Authorization: Bearer $MCP_TOKEN`. It also serves the web app's `/api/parts` and `/api/design` (a model designs a project from a prompt: OpenAI, then DeepSeek if OpenAI runs out, using `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`). Its exports go to the `designs` volume, so `https://$DOMAIN/?design=out/<title>` shows them right away. |
| `studio` | Circuit Studio, Senna's Streamlit app (`circuit-studio/`), at `https://$DOMAIN/studio/`: reference photos + wiring notes go to Gemini (`GEMINI_API_KEY`, `GEMINI_STUDIO_MODEL`) and come back as a labelled breadboard GLB. |

## First deploy

1. **Server.** On Vultr, deploy a Cloud Compute instance from the Marketplace **Docker** image (Ubuntu with Docker preinstalled). 1 vCPU / 2 GB is enough. Allow ports 22, 80 and 443 in the firewall group.
2. **DNS.** At GoDaddy, add an `A` record for the domain (or a subdomain) pointing at the instance's IPv4 address. Wait until `ping <domain>` shows that IP: Caddy needs it to get the certificate.
3. **Code and settings** (on the server, over SSH):
   ```sh
   git clone https://github.com/flyingf15h/Physical-Studio-Code.git
   cd Physical-Studio-Code/deploy
   cp .env.example .env
   nano .env          # DOMAIN (one name or a comma-separated list), GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, MCP_TOKEN (openssl rand -hex 24), optional DEMO_CODE
   chmod 600 .env
   docker compose up -d --build
   ```
4. **Check.**
   - `https://<domain>/healthz` says `ok`.
   - `https://<domain>/` shows the sample guide; "Watch my bench" asks for the camera.
   - `docker compose logs -f` if something's off. A certificate error at first usually means DNS hasn't propagated yet.

## Use the hosted MCP server from Claude Code

```sh
claude mcp add --transport http physical-studio-hosted https://<domain>/mcp \
  --header "Authorization: Bearer <MCP_TOKEN>"
```

Exports then appear at `https://<domain>/?design=out/<design title>`. Hand out the token like a password: anyone with it can run designs on the server.

## Update

```sh
cd Physical-Studio-Code && git pull && cd deploy && docker compose up -d --build
```

## Test locally

`DOMAIN=localhost` makes Caddy use a local self-signed certificate (your browser will warn once). If ports 80/443 are taken, add an override file with `ports: !override ["18080:80", "18443:443"]` for `caddy`.

```sh
cd deploy && DOMAIN=localhost MCP_TOKEN=test docker compose up -d --build
curl -k https://localhost/healthz
```

## Notes

- Everyone shares one Gemini key and its quota. `TOKENS_PER_MINUTE` (default 6 per IP) and `DEMO_CODE` keep strangers from using it up.
- The MCP server keeps a single design in memory, so it serves one designer at a time (fine for a demo).
- `.env` is gitignored. Never commit it or paste it into chat or huddle.

## Updating the server

On the box (SSH, or Vultr's web console), as root:

```sh
sh /opt/Physical-Studio-Code/deploy/update.sh
```

It pulls, rebuilds and restarts everything. Give it a domain list to change `DOMAIN` at the same time:

```sh
sh /opt/Physical-Studio-Code/deploy/update.sh "physicalstudio.work, www.physicalstudio.work, 155-138-154-8.sslip.io"
```

For a new domain, first add DNS records at the registrar (GoDaddy: My Products → the domain → DNS): an `A` record for `@` pointing at the server's IP (155.138.154.8) and a `CNAME` for `www` pointing at `@`, and delete GoDaddy's default "Parked" `A` record.

## Backups

`deploy/backup.sh` saves the designs volume (accounts, saved projects, BOM parts, every build with its photos and commits, step reports) to `/var/backups/physical-studio/`, leaving out the ready-made guides because they're in the repo. It keeps 7 days.

```sh
sh /opt/Physical-Studio-Code/deploy/backup.sh install   # back up now and every night at 04:17 UTC
```

Step reports ("Something wrong with this step?") are in `.reports/reports.jsonl` inside the volume:
`cat /var/lib/docker/volumes/physical-studio_designs/_data/.reports/reports.jsonl`.

The backups are on the same server, so they don't survive losing the server. To copy them off it, download the newest file now and then (`scp root@<server>:/var/backups/physical-studio/designs-*.tar.gz .`), or sync the folder to free object storage (Cloudflare R2's free tier is 10 GB).
