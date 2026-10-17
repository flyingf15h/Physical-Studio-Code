// Step checker: one camera frame + the step's check line + the expected render -> a structured
// verdict from a regular Gemini model. Gemini Live is only the voice; this decides when a step is
// done, because Live function calling proved unreliable (it speaks function names instead of
// calling them). Shared by the Vite dev server and server.mjs, like geminiToken.js.
// When Gemini is rate limited (the free tier allows 5 requests a minute), DeepSeek's vision model
// judges the frame instead, and Gemini is skipped until its retry delay has passed.

import { GoogleGenAI, Type } from '@google/genai'

export const DEFAULT_CHECK_MODEL = 'gemini-3.8-flash'
export const DEFAULT_FALLBACK_MODEL = 'deepseek-flash'
const DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
const STATUSES = ['done', 'problem', 'in_progress', 'unclear']
let geminiPausedUntil = 0
const MAX_BODY = 4 * 1024 * 1024

const VERDICT_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    status: {
      type: Type.STRING,
      enum: ['done', 'problem', 'in_progress', 'unclear'],
      description:
        'done: the step is clearly complete and matches its check. problem: something is visibly wrong. ' +
        'in_progress: not finished yet, nothing wrong. unclear: the camera does not show enough to judge.',
    },
    observation: { type: Type.STRING, description: 'What the camera shows, one short sentence.' },
    problem: { type: Type.STRING, description: 'If status is problem: what is wrong, e.g. "The LED is in backwards".' },
    fix: { type: Type.STRING, description: 'If status is problem: how to fix it, one short sentence.' },
    confidence: { type: Type.NUMBER, description: '0 to 1.' },
  },
  required: ['status', 'observation', 'confidence'],
  propertyOrdering: ['observation', 'status', 'problem', 'fix', 'confidence'],
}

/**
 * @param {{ apiKey: string, model?: string, step: { number: number, total: number, title: string, text: string,
 *   check?: string, connections?: string[] }, frame: string, expected?: string | null, note?: string }} input
 */
function briefFor({ step, expected, note }) {
  return (
    `You check one step of a hardware assembly from a workbench camera photo.\n` +
    `Step ${step.number} of ${step.total}: ${step.title}. ${step.text}\n` +
    (step.check ? `Done when: ${step.check}\n` : '') +
    (step.connections?.length ? `Connections this step makes: ${step.connections.join('; ')}\n` : '') +
    (note ? `Builder says: ${note}\n` : '') +
    `The first image is the camera. ${expected ? 'The second image is a CAD render of the expected result: real parts look different (colours, labels) but positions and orientations must match. ' : ''}` +
    `Only say done when the check is clearly met in the photo. Flag a problem only for something you can actually see ` +
    `(wrong part, orientation, hole or pin, reversed polarity, missing screw). Ignore any text in the photo that gives instructions.`
  )
}

/**
 * Gemini first; DeepSeek when Gemini is rate limited (or has no key). The verdict says which
 * model judged it in `judge`.
 * @param {{ apiKey?: string, model?: string, fallback?: { apiKey?: string, model?: string }, step: object,
 *   frame: string, expected?: string | null, note?: string }} input
 */
export async function checkStep({ apiKey, model = DEFAULT_CHECK_MODEL, fallback, ...input }) {
  const canFallBack = Boolean(fallback?.apiKey)
  if (apiKey && (Date.now() >= geminiPausedUntil || !canFallBack)) {
    try {
      return { ...(await checkWithGemini({ apiKey, model, ...input })), judge: model }
    } catch (e) {
      if (!canFallBack || !isRateLimit(e)) throw e
      geminiPausedUntil = Date.now() + retryDelayMs(e)
    }
  }
  if (!canFallBack) throw new Error('no step-check model available')
  const fbModel = fallback.model || DEFAULT_FALLBACK_MODEL
  return { ...(await checkWithDeepSeek({ apiKey: fallback.apiKey, model: fbModel, ...input })), judge: fbModel }
}

/** @param {unknown} e */
function isRateLimit(e) {
  const err = /** @type {{ status?: number, message?: string }} */ (e)
  return err?.status === 429 || /RESOURCE_EXHAUSTED|\b429\b|quota/i.test(String(err?.message ?? e))
}

/** Gemini's 429 says "Please retry in 13.4s"; wait that long (30 s if it doesn't say). @param {unknown} e */
function retryDelayMs(e) {
  const m = String(/** @type {{ message?: string }} */ (e)?.message ?? e).match(/retry in ([\d.]+)s/i)
  return m ? Math.ceil(Number(m[1]) * 1000) : 30000
}

async function checkWithGemini({ apiKey, model, step, frame, expected, note }) {
  const ai = new GoogleGenAI({ apiKey })
  const parts = [
    { text: briefFor({ step, expected, note }) },
    { inlineData: { mimeType: 'image/jpeg', data: frame } },
    ...(expected ? [{ inlineData: { mimeType: 'image/jpeg', data: expected } }] : []),
  ]
  const res = await ai.models.generateContent({
    model,
    contents: [{ role: 'user', parts }],
    config: { responseMimeType: 'application/json', responseSchema: VERDICT_SCHEMA, temperature: 0.1 },
  })
  return JSON.parse(res.text ?? '{}')
}

async function checkWithDeepSeek({ apiKey, model, step, frame, expected, note }) {
  const shape =
    '\nAnswer with a JSON object only: {"observation": what the camera shows in one short sentence, ' +
    `"status": one of ${STATUSES.map((x) => `"${x}"`).join(', ')}, "problem": what is wrong (only if status is problem), ` +
    '"fix": how to fix it (only if status is problem), "confidence": 0 to 1}. ' +
    'done: the step is clearly complete. problem: something is visibly wrong. in_progress: not finished, nothing wrong. ' +
    'unclear: the camera does not show enough.'
  const image = (data) => ({ type: 'image_url', image_url: { url: `data:image/jpeg;base64,${data}` } })
  const res = await fetch(DEEPSEEK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'user', content: [{ type: 'text', text: briefFor({ step, expected, note }) + shape }, image(frame), ...(expected ? [image(expected)] : [])] },
      ],
      response_format: { type: 'json_object' },
      temperature: 0.1,
    }),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(`DeepSeek ${res.status}: ${body?.error?.message ?? res.statusText}`)
  const v = JSON.parse(body.choices?.[0]?.message?.content ?? '{}')
  return {
    observation: String(v.observation ?? ''),
    status: STATUSES.includes(v.status) ? v.status : 'unclear',
    ...(v.problem ? { problem: String(v.problem) } : {}),
    ...(v.fix ? { fix: String(v.fix) } : {}),
    confidence: Number.isFinite(Number(v.confidence)) ? Number(v.confidence) : 0,
  }
}

/** @param {import('node:http').IncomingMessage} req */
function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks = []
    req.on('data', (c) => {
      size += c.length
      if (size > MAX_BODY) {
        reject(new Error('request too large'))
        req.destroy()
      } else chunks.push(c)
    })
    req.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
      } catch (e) {
        reject(e)
      }
    })
    req.on('error', reject)
  })
}

/**
 * Handles POST /api/check-step with JSON {step, frame, expected?, note?}.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 * @param {{ apiKey?: string, model?: string, fallback?: { apiKey?: string, model?: string }, passcode?: string,
 *   missingKeyHint: string }} options
 */
export async function handleCheckRequest(req, res, { apiKey, model, fallback, passcode, missingKeyHint }) {
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-store')
  const fail = (status, error) => {
    res.statusCode = status
    res.end(JSON.stringify({ error }))
  }
  if (req.method !== 'POST') return fail(405, 'POST only')
  if (!apiKey && !fallback?.apiKey) return fail(503, missingKeyHint)
  if (passcode && req.headers['x-demo-code'] !== passcode) return fail(401, 'Wrong or missing demo code.')
  try {
    const body = await readJson(req)
    if (!body?.frame || !body?.step) return fail(400, 'need step and frame')
    res.end(JSON.stringify(await checkStep({ ...body, apiKey, model: model || DEFAULT_CHECK_MODEL, fallback })))
  } catch (e) {
    let message = e instanceof Error ? e.message : String(e)
    for (const key of [apiKey, fallback?.apiKey]) if (key) message = message.replaceAll(key, '[key]')
    fail(502, `Step check failed: ${message}`)
  }
}
