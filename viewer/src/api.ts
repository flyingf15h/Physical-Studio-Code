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
  designer: string | null // which model is designing: OpenAI, DeepSeek or Claude
  attachments?: { images: string[]; links: { url: string; error: string | null }[] }
}

/** What the user attached to the prompt: images as data URLs, links as http(s) URLs. */
export interface DesignInputs {
  images?: string[]
  links?: string[]
}

function headers(json = false): Record<string, string> {
  return {
    'x-demo-code': designParams().code ?? '',
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  }
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.error ?? `${url}: ${res.status}`)
  return body as T
}

export const listParts = () => call<PartSummary[]>('/api/parts')

export const startDesign = (prompt: string, inputs: DesignInputs = {}) =>
  call<{ id: string }>('/api/design', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ prompt, ...inputs }),
  })

export const getDesign = (id: string) => call<DesignJob>(`/api/design/${encodeURIComponent(id)}`)
