import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

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

export default defineConfig({
  plugins: [react(), serveExports()],
})
