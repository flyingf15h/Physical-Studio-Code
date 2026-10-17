import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { handleTokenRequest } from './server/geminiToken.js'

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
// Same handler as the production server (server.mjs).
function geminiToken(env: Record<string, string>): Plugin {
  return {
    name: 'gemini-token',
    configureServer(server) {
      server.middlewares.use('/api/gemini-token', (req, res) =>
        handleTokenRequest(req, res, {
          apiKey: env.GEMINI_API_KEY,
          model: env.GEMINI_LIVE_MODEL,
          passcode: env.DEMO_CODE,
          missingKeyHint: 'Set GEMINI_API_KEY in viewer/.env.local and restart npm run dev.',
        }),
      )
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '') // '' prefix: server-side only, never sent to the page
  return {
    plugins: [react(), serveExports(), geminiToken(env)],
  }
})
