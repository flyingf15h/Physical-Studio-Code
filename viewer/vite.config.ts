import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { handleTokenRequest } from './server/geminiToken.js'
import { handleCheckRequest } from './server/stepCheck.js'

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
      server.middlewares.use('/api/check-step', (req, res) =>
        handleCheckRequest(req, res, {
          apiKey: env.GEMINI_API_KEY,
          model: env.GEMINI_CHECK_MODEL,
          fallback: { apiKey: env.DEEPSEEK_API_KEY, model: env.DEEPSEEK_CHECK_MODEL },
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
    // Design jobs and the parts list live in the MCP server's HTTP app:
    //   cd mcp-server && MCP_TRANSPORT=http MCP_TOKEN=dev ANTHROPIC_API_KEY=... uv run physical-studio-mcp
    server: {
      proxy: {
        '/api/parts': env.MCP_HTTP_URL || 'http://localhost:8000',
        '/api/design': env.MCP_HTTP_URL || 'http://localhost:8000',
      },
    },
  }
})
