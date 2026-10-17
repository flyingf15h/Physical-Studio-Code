// Smoke test against the real Gemini API (not the mocked socket in the unit tests), with the same
// code the server runs: geminiToken.js mints a Live token, a Live session opens with it the way
// src/tracker/session.ts does, and stepCheck.js judges a frame.
//
//   node scripts/gemini-smoke.mjs                      # every key, Live round trip, blank-frame check
//   node scripts/gemini-smoke.mjs --frame bench.jpg --step 4 --expect problem
//
// Keys come from GEMINI_API_KEY / GEMINI_API_KEYS in the environment or viewer/.env.local.
// --frame judges a real bench photo against a step of --design (default public/traffic-light) and
// fails unless the verdict is --expect (done | problem | in_progress | unclear). Exits 1 on any failure.

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { GoogleGenAI, Modality } from '@google/genai'
import { geminiKeys, redact, withGeminiKey } from '../server/geminiKeys.js'
import { DEFAULT_LIVE_MODEL, mintLiveToken } from '../server/geminiToken.js'
import { checkStep, DEFAULT_CHECK_MODEL } from '../server/stepCheck.js'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
// 64x48 plain grey JPEG: nothing to see, so the checker must never call it done.
const BLANK =
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDARESEhgVGC8aGi9jQjhCY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2NjY2P/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD/2Q=='

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((a, i, all) => (a.startsWith('--') ? [[a.slice(2), all[i + 1]]] : [])),
)

function loadEnv() {
  const env = { ...process.env }
  const file = join(ROOT, '.env.local')
  if (existsSync(file)) {
    for (const line of readFileSync(file, 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/)
      if (m && !env[m[1]]) env[m[1]] = m[2].replace(/^["']|["']$/g, '')
    }
  }
  return env
}

const env = loadEnv()
const keys = geminiKeys(env)
const liveModel = env.GEMINI_LIVE_MODEL || DEFAULT_LIVE_MODEL
const checkModel = env.GEMINI_CHECK_MODEL || DEFAULT_CHECK_MODEL
const hide = (e) => redact(e instanceof Error ? e.message : String(e), keys)
let failed = 0
const report = (ok, name, detail) => {
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `: ${detail}` : ''}`)
}

if (!keys.length) {
  console.log('No Gemini key: set GEMINI_API_KEY or GEMINI_API_KEYS (env or viewer/.env.local).')
  process.exit(1)
}
console.log(`${keys.length} Gemini key(s); live ${liveModel}, check ${checkModel}`)

// 1. Each key on its own, so a dead key shows up before the demo does. A model lookup checks the
// key without spending any of its daily quota (free tier: 20 generate requests a day per project).
for (const [i, apiKey] of keys.entries()) {
  try {
    const m = await new GoogleGenAI({ apiKey }).models.get({ model: checkModel })
    report(true, `key ${i + 1}`, m.name)
  } catch (e) {
    report(false, `key ${i + 1}`, hide(e).slice(0, 160))
  }
}

// 2. Live: mint a single-use token, open a session with it like the browser does, get a reply.
try {
  const { token, model } = await withGeminiKey(keys, (apiKey) => mintLiveToken({ apiKey, model: liveModel }), {
    includePaused: true,
  })
  const ai = new GoogleGenAI({ apiKey: token, httpOptions: { apiVersion: 'v1alpha' } })
  let session
  const heard = await new Promise((resolve, reject) => {
    let text = ''
    const timer = setTimeout(() => reject(new Error('no reply within 30 s')), 30000)
    ai.live
      .connect({
        model,
        config: { responseModalities: [Modality.AUDIO], outputAudioTranscription: {} },
        callbacks: {
          onmessage: (m) => {
            text += m.serverContent?.outputTranscription?.text ?? ''
            if (m.serverContent?.turnComplete) {
              clearTimeout(timer)
              resolve(text)
            }
          },
          onerror: (e) => reject(new Error(e.message ?? 'Live connection error')),
          onclose: (e) => reject(new Error(`Live closed${e.reason ? `: ${e.reason}` : ''}`)),
        },
      })
      .then((s) => {
        session = s
        s.sendClientContent({ turns: [{ role: 'user', parts: [{ text: 'Say: ready to build.' }] }] })
      }, reject)
  }).finally(() => session?.close())
  report(Boolean(heard.trim()), 'live token + session', JSON.stringify(heard.trim().slice(0, 60)))
} catch (e) {
  report(false, 'live token + session', hide(e))
}

// 3. Step check on a frame of a traffic-light step.
const design = JSON.parse(readFileSync(join(ROOT, args.design ?? 'public/traffic-light', 'design.steps.json'), 'utf8'))
const n = Number(args.step ?? 4)
const s = design.steps.find((x) => x.index === n) ?? design.steps[0]
const step = { number: s.index, total: design.steps.length, title: s.title, text: s.text, check: s.check }
const frame = args.frame ? readFileSync(args.frame).toString('base64') : BLANK
try {
  const v = await checkStep({ apiKeys: keys, model: checkModel, step, frame })
  const ok = args.expect ? v.status === args.expect : v.status !== 'done'
  const said = [v.status, v.observation, v.problem, v.fix].filter(Boolean).join(' | ')
  report(ok, `step ${step.number} check (${args.frame ?? 'blank frame'}${args.expect ? `, expect ${args.expect}` : ''})`, said)
} catch (e) {
  report(false, `step ${step.number} check`, hide(e))
}

console.log(failed ? `${failed} failed` : 'all passed')
process.exit(failed ? 1 : 0)
