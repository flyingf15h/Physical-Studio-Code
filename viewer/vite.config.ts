import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { GoogleGenAI } from '@google/genai'

// Serves the MCP server's exports at /out/<design>/..., so `?design=out/<design>` shows
// whatever Claude exported last without copying files.
const OUT_DIR = path.resolve(import.meta.dirname, '../mcp-server/out')

function serveExports(): Plugin {
  return {
    name: 'serve-mcp-exports',
    configureServer(server) {
      server.middlewares.use('/out', (req, res, next) => {
        const file = path.join(OUT_DIR, decodeURIComponent((req.url ?? '/').split('?')[0]))
        if (!file.startsWith(OUT_DIR + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return next()
        res.setHeader('Cache-Control', 'no-store')
        res.setHeader('Content-Type', file.endsWith('.json') ? 'application/json' : 'model/gltf-binary')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

// POST /api/gemini-token mints a short-lived Gemini Live token, so the browser streams the
// camera straight to Gemini without ever seeing GEMINI_API_KEY (read from viewer/.env.local).
function geminiToken(env: Record<string, string>): Plugin {
  const model = env.GEMINI_LIVE_MODEL || 'gemini-3.8-live'
  return {
    name: 'gemini-token',
    configureServer(server) {
      server.middlewares.use('/api/gemini-token', async (req, res) => {
        res.setHeader('Content-Type', 'application/json')
        if (req.method !== 'POST') {
          res.statusCode = 405
          return res.end(JSON.stringify({ error: 'POST only' }))
        }
        if (!env.GEMINI_API_KEY) {
          res.statusCode = 503
          return res.end(JSON.stringify({ error: 'Set GEMINI_API_KEY in viewer/.env.local and restart npm run dev.' }))
        }
        try {
          const ai = new GoogleGenAI({ apiKey: env.GEMINI_API_KEY, httpOptions: { apiVersion: 'v1alpha' } })
          const token = await ai.authTokens.create({
            config: {
              uses: 1,
              expireTime: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
              newSessionExpireTime: new Date(Date.now() + 60 * 1000).toISOString(),
              liveConnectConstraints: { model },
              httpOptions: { apiVersion: 'v1alpha' },
            },
          })
          res.end(JSON.stringify({ token: token.name, model }))
        } catch (e) {
          res.statusCode = 502
          const message = (e instanceof Error ? e.message : String(e)).replaceAll(env.GEMINI_API_KEY, '[key]')
          res.end(JSON.stringify({ error: `Gemini token request failed: ${message}` }))
        }
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '') // '' prefix: server-side only, never sent to the page
  return {
    plugins: [react(), serveExports(), geminiToken(env)],
  }
})
