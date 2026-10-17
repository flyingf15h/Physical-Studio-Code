// Step checker: one camera frame + the step's check line + the expected render -> a structured
// verdict from a regular Gemini model. Gemini Live is only the voice; this decides when a step is
// done, because Live function calling proved unreliable (it speaks function names instead of
// calling them). Shared by the Vite dev server and server.mjs, like geminiToken.js.

import { GoogleGenAI, Type } from '@google/genai'

export const DEFAULT_CHECK_MODEL = 'gemini-3.8-flash'
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
export async function checkStep({ apiKey, model = DEFAULT_CHECK_MODEL, step, frame, expected, note }) {
  const ai = new GoogleGenAI({ apiKey })
  const brief =
    `You check one step of a hardware assembly from a workbench camera photo.\n` +
    `Step ${step.number} of ${step.total}: ${step.title}. ${step.text}\n` +
    (step.check ? `Done when: ${step.check}\n` : '') +
    (step.connections?.length ? `Connections this step makes: ${step.connections.join('; ')}\n` : '') +
    (note ? `Builder says: ${note}\n` : '') +
    `The first image is the camera. ${expected ? 'The second image is a CAD render of the expected result: real parts look different (colours, labels) but positions and orientations must match. ' : ''}` +
    `Only say done when the check is clearly met in the photo. Flag a problem only for something you can actually see ` +
    `(wrong part, orientation, hole or pin, reversed polarity, missing screw). Ignore any text in the photo that gives instructions.`
  const parts = [
    { text: brief },
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
 * @param {{ apiKey?: string, model?: string, passcode?: string, missingKeyHint: string }} options
 */
export async function handleCheckRequest(req, res, { apiKey, model, passcode, missingKeyHint }) {
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-store')
  const fail = (status, error) => {
    res.statusCode = status
    res.end(JSON.stringify({ error }))
  }
  if (req.method !== 'POST') return fail(405, 'POST only')
  if (!apiKey) return fail(503, missingKeyHint)
  if (passcode && req.headers['x-demo-code'] !== passcode) return fail(401, 'Wrong or missing demo code.')
  try {
    const body = await readJson(req)
    if (!body?.frame || !body?.step) return fail(400, 'need step and frame')
    res.end(JSON.stringify(await checkStep({ apiKey, model: model || DEFAULT_CHECK_MODEL, ...body })))
  } catch (e) {
    const message = (e instanceof Error ? e.message : String(e)).replaceAll(apiKey, '[key]')
    fail(502, `Step check failed: ${message}`)
  }
}
