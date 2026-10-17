// Several Gemini keys, taken in turn so no single key's quota runs out. GEMINI_API_KEYS=k1,k2,k3
// (GEMINI_API_KEY still works, alone or alongside). A key that gets rate limited sits out until its
// retry delay passes, and the request moves on to the next key. Shared by geminiToken.js and
// stepCheck.js, in both the Vite dev server and server.mjs.

/** All configured keys, without duplicates. @param {Record<string, string | undefined>} env */
export function geminiKeys(env) {
  const keys = [...(env.GEMINI_API_KEYS ?? '').split(','), env.GEMINI_API_KEY ?? '']
  return [...new Set(keys.map((k) => k.trim()).filter(Boolean))]
}

let turn = 0
/** @type {Map<string, number>} key -> time it may be used again */
const pausedUntil = new Map()

/**
 * Keys to try for one request, in order: starting one past the previous request's first key, and
 * skipping keys that are sitting out. With `includePaused`, those come last instead of being
 * skipped (for when there's no fallback model to hand the request to).
 * @param {string[]} keys
 * @param {{ includePaused?: boolean }} [options]
 */
export function keysInTurn(keys, { includePaused = false } = {}) {
  if (!keys.length) return []
  const start = turn++ % keys.length
  const order = [...keys.slice(start), ...keys.slice(0, start)]
  const now = Date.now()
  const ready = order.filter((k) => (pausedUntil.get(k) ?? 0) <= now)
  return includePaused ? [...ready, ...order.filter((k) => !ready.includes(k))] : ready
}

/** @param {string} key @param {number} ms */
export function pauseKey(key, ms) {
  pausedUntil.set(key, Date.now() + ms)
}

/** @param {unknown} e */
export function isRateLimit(e) {
  const err = /** @type {{ status?: number, message?: string }} */ (e)
  return err?.status === 429 || /RESOURCE_EXHAUSTED|\b429\b|quota/i.test(String(err?.message ?? e))
}

/** Gemini's 429 says "Please retry in 13.4s"; wait that long (30 s if it doesn't say). @param {unknown} e */
export function retryDelayMs(e) {
  const m = String(/** @type {{ message?: string }} */ (e)?.message ?? e).match(/retry in ([\d.]+)s/i)
  return m ? Math.ceil(Number(m[1]) * 1000) : 30000
}

/**
 * Runs `call` with each key in turn until one isn't rate limited. Other errors stop right away.
 * Throws the last rate-limit error when every key is rate limited.
 * @template T
 * @param {string[]} keys
 * @param {(key: string) => Promise<T>} call
 * @param {{ includePaused?: boolean }} [options]
 * @returns {Promise<T>}
 */
export async function withGeminiKey(keys, call, options) {
  let last = Object.assign(new Error('every Gemini key is rate limited; try again in a minute'), { status: 429 })
  for (const key of keysInTurn(keys, options)) {
    try {
      return await call(key)
    } catch (e) {
      if (!isRateLimit(e)) throw e
      pauseKey(key, retryDelayMs(e))
      last = /** @type {Error} */ (e)
    }
  }
  throw last
}

/** Replaces every key in a message with [key]. @param {string} message @param {(string | undefined)[]} keys */
export function redact(message, keys) {
  for (const key of keys) if (key) message = message.replaceAll(key, '[key]')
  return message
}
