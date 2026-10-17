// Mints single-use Gemini Live tokens so the browser can stream to Gemini without ever seeing
// GEMINI_API_KEY. Shared by the Vite dev server (vite.config.ts) and the production server
// (server.mjs). Plain JS so both can import it without a build step.

import { GoogleGenAI } from '@google/genai'

export const DEFAULT_LIVE_MODEL = 'gemini-3.8-live'

/**
 * @param {{ apiKey: string, model?: string }} options
 * @returns {Promise<{ token: string, model: string }>}
 */
export async function mintLiveToken({ apiKey, model = DEFAULT_LIVE_MODEL }) {
  // The SDK only supports ephemeral tokens on v1alpha.
  const ai = new GoogleGenAI({ apiKey, httpOptions: { apiVersion: 'v1alpha' } })
  const token = await ai.authTokens.create({
    config: {
      uses: 1,
      expireTime: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
      newSessionExpireTime: new Date(Date.now() + 60 * 1000).toISOString(),
      liveConnectConstraints: { model },
      httpOptions: { apiVersion: 'v1alpha' },
    },
  })
  if (!token.name) throw new Error('Gemini returned no token')
  return { token: token.name, model }
}

/**
 * Handles POST /api/gemini-token on a plain Node request/response pair.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 * @param {{ apiKey?: string, model?: string, passcode?: string, missingKeyHint: string }} options
 */
export async function handleTokenRequest(req, res, { apiKey, model, passcode, missingKeyHint }) {
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-store')
  const fail = (status, error) => {
    res.statusCode = status
    res.end(JSON.stringify({ error }))
  }
  if (req.method !== 'POST') return fail(405, 'POST only')
  if (!apiKey) return fail(503, missingKeyHint)
  if (passcode && req.headers['x-demo-code'] !== passcode) {
    return fail(401, 'This demo needs a code: open the page with ?code=<the code> in the address.')
  }
  try {
    res.end(JSON.stringify(await mintLiveToken({ apiKey, model: model || DEFAULT_LIVE_MODEL })))
  } catch (e) {
    const message = (e instanceof Error ? e.message : String(e)).replaceAll(apiKey, '[key]')
    fail(502, `Gemini token request failed: ${message}`)
  }
}
