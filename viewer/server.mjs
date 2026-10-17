// Production server for the viewer: serves the built app (dist/), the Gemini Live token
// endpoint and the MCP server's exports. Node built-ins only, plus @google/genai for tokens.
//
//   npm run build && GEMINI_API_KEY=... node server.mjs
//
// Env: PORT (8080), GEMINI_API_KEY, GEMINI_LIVE_MODEL, DEMO_CODE (if set, the token endpoint
// needs the page opened with ?code=<DEMO_CODE>), OUT_DIR (exports, default ../mcp-server/out),
// TOKENS_PER_MINUTE (per client IP, default 6), GEMINI_CHECK_MODEL, CHECKS_PER_MINUTE (default 30).

import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { handleTokenRequest } from './server/geminiToken.js'
import { handleCheckRequest } from './server/stepCheck.js'

const ROOT = import.meta.dirname
const DIST = path.join(ROOT, 'dist')
const OUT_DIR = path.resolve(process.env.OUT_DIR ?? path.join(ROOT, '../mcp-server/out'))
const PORT = Number(process.env.PORT ?? 8080)
const TOKENS_PER_MINUTE = Number(process.env.TOKENS_PER_MINUTE ?? 6)
const CHECKS_PER_MINUTE = Number(process.env.CHECKS_PER_MINUTE ?? 30)

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.glb': 'model/gltf-binary',
  '.stl': 'model/stl',
  '.step': 'model/step',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
}

// Tokens and step checks spend our Gemini quota, so cap how fast one client can ask.
const recent = new Map()
function allow(bucket, ip, perMinute) {
  const key = `${bucket}:${ip}`
  const now = Date.now()
  const hits = (recent.get(key) ?? []).filter((t) => now - t < 60_000)
  if (hits.length >= perMinute) return false
  hits.push(now)
  recent.set(key, hits)
  return true
}

function clientIp(req) {
  return String(req.headers['x-forwarded-for'] ?? req.socket.remoteAddress ?? '').split(',')[0].trim()
}

function sendFile(res, file, cache) {
  res.setHeader('Content-Type', TYPES[path.extname(file)] ?? 'application/octet-stream')
  res.setHeader('Cache-Control', cache)
  fs.createReadStream(file).pipe(res)
}

function inside(dir, urlPath) {
  const file = path.join(dir, decodeURIComponent(urlPath))
  return file.startsWith(dir + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile() ? file : null
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost')

  if (url.pathname === '/healthz') return res.end('ok')

  if (url.pathname === '/api/check-step') {
    if (req.method === 'POST' && !allow('check', clientIp(req), CHECKS_PER_MINUTE)) {
      res.statusCode = 429
      return res.end(JSON.stringify({ error: 'Too many step checks; slow down.' }))
    }
    return handleCheckRequest(req, res, {
      apiKey: process.env.GEMINI_API_KEY,
      model: process.env.GEMINI_CHECK_MODEL,
      passcode: process.env.DEMO_CODE,
      missingKeyHint: 'The server has no GEMINI_API_KEY; set it in deploy/.env and restart.',
    })
  }

  if (url.pathname === '/api/gemini-token') {
    if (req.method === 'POST' && !allow('token', clientIp(req), TOKENS_PER_MINUTE)) {
      res.statusCode = 429
      return res.end(JSON.stringify({ error: 'Too many camera sessions started; wait a minute.' }))
    }
    return handleTokenRequest(req, res, {
      apiKey: process.env.GEMINI_API_KEY,
      model: process.env.GEMINI_LIVE_MODEL,
      passcode: process.env.DEMO_CODE,
      missingKeyHint: 'The server has no GEMINI_API_KEY; set it in deploy/.env and restart.',
    })
  }

  if (url.pathname.startsWith('/out/')) {
    const file = inside(OUT_DIR, url.pathname.slice('/out'.length))
    if (file) return sendFile(res, file, 'no-store') // exports change whenever Claude re-exports
    res.statusCode = 404
    return res.end('not found')
  }

  const file = inside(DIST, url.pathname === '/' ? '/index.html' : url.pathname)
  if (file) return sendFile(res, file, file.includes(`${path.sep}assets${path.sep}`) ? 'public, max-age=31536000, immutable' : 'no-cache')
  sendFile(res, path.join(DIST, 'index.html'), 'no-cache') // single-page app
})

server.listen(PORT, () => console.log(`viewer on :${PORT}, exports from ${OUT_DIR}`))
