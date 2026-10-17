// Client for the design backend (mcp-server/physical_studio/jobs.py, served by the MCP server's
// HTTP app; Caddy and the Vite dev server route /api/parts and /api/design* to it).

import { designParams } from './router'

export interface PartSummary {
  id: string
  name: string
  category: 'board' | 'input' | 'output' | 'fastener' | 'misc'
  body_size: [number, number, number]
  verified: boolean
  source?: string
}

export type JobEventKind =
  'parts' | 'place' | 'case' | 'wire' | 'check' | 'fix' | 'steps' | 'note' | 'preview' | 'done' | 'error'

export interface JobEvent {
  t: number // seconds since the job started
  kind: JobEventKind
  text: string
  image?: string // preview PNG url (kind "preview")
}

export interface JobChecks {
  interference: { ok: boolean; problems: number } | null
  clearance: { ok: boolean; notes: string[] } | null
  printer: { ok: boolean; size_mm: [number, number, number] } | null
}

export interface DesignJob {
  id: string
  prompt: string
  status: 'queued' | 'running' | 'done' | 'error'
  title: string | null
  events: JobEvent[]
  preview: string | null // latest preview PNG url
  design: string | null // "out/<id>", for /guide?design= and /print?design=
  checks: JobChecks
  error: string | null
  designer: string | null // which model is designing: OpenAI, DeepSeek, Gemini or Claude
  attachments?: { images: string[]; links: { url: string; error: string | null }[] }
}

/** What the user attached to the prompt: images as data URLs, links as http(s) URLs. */
export interface DesignInputs {
  images?: string[]
  links?: string[]
  model?: string // a Provider id to go first; the others stay as fallbacks
}

/** A design model the server has a key for. */
export interface Provider {
  id: string // openai, deepseek, gemini, anthropic
  label: string
}

function headers(json = false): Record<string, string> {
  return {
    'x-demo-code': designParams().code ?? '',
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  }
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(body?.error ?? `${url}: ${res.status}`)
  // e.g. the app's own index.html when no API server is behind it: an error, not an empty result
  if (body === null) throw new Error(`${url}: the server didn't answer with JSON`)
  return body as T
}

export const listParts = () => call<PartSummary[]>('/api/parts')

/** The server's design models, its default first. */
export const listProviders = () => call<Provider[]>('/api/design/providers')

export const startDesign = (prompt: string, inputs: DesignInputs = {}) =>
  call<{ id: string }>('/api/design', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ prompt, ...inputs }),
  })

export const getDesign = (id: string) => call<DesignJob>(`/api/design/${encodeURIComponent(id)}`)
