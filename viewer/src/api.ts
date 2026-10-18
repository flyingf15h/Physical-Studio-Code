// Client for the design backend (mcp-server/physical_studio/jobs.py, served by the MCP server's
// HTTP app; Caddy and the Vite dev server route /api/parts and /api/design* to it).

import { authToken, type User } from './auth'
import { designParams } from './router'

export interface PartSummary {
  id: string
  name: string
  category: 'board' | 'input' | 'output' | 'fastener' | 'misc'
  body_size: [number, number, number]
  verified: boolean
  source?: string
  mine?: boolean // from the signed-in user's BOM
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
  const token = authToken()
  return {
    'x-demo-code': designParams().code ?? '',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

export const listParts = () => call<PartSummary[]>('/api/parts', { headers: headers() })

/** The server's design models, its default first. */
export const listProviders = () => call<Provider[]>('/api/design/providers')

export const startDesign = (prompt: string, inputs: DesignInputs = {}) =>
  call<{ id: string }>('/api/design', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ prompt, ...inputs }),
  })

export const getDesign = (id: string) => call<DesignJob>(`/api/design/${encodeURIComponent(id)}`)

/** A personal key for the visitor's own AI (POST /api/connect, accounts.py) and the MCP address. */
export const connectKey = () => call<{ key: string; mcp_url: string }>('/api/connect', { method: 'POST' })

export interface ExportedProject {
  design: string // "out/<folder>"
  title: string
  prompt?: string
  steps?: number
  at: number // seconds
}

/** Guides the visitor's AI exported with their key, newest first. */
export const listMyProjects = (key: string) =>
  call<ExportedProject[]>('/api/my-projects', { headers: { Authorization: `Bearer ${key}` } })

// --- Breadboard builds from bench photos (mcp-server/physical_studio/bench/, ported from Senna's
// Build helper in circuit-studio/). Contract agreed with Senna's Claude.

export interface BenchModel {
  glb: string // url of a GLB whose nodes are named <id>__mesh
  labels: { id: string; name: string; kind: string }[]
  new?: string[] // ids placed in this step (step models only)
}

export interface Verdict {
  observation: string
  status: 'done' | 'problem' | 'in_progress' | 'unclear' | 'error'
  problem: string
  fix: string
  confidence: number
}

export interface BuildStep {
  number: number
  title: string
  instruction: string
  check: string
  part_ids: string[]
  placements: { what: string; hole: string; where: string }[]
  picture: string | null // url of the step's numbered-hole SVG
  markers: [number, string, string, string][] // [n, what, where, hole]
  model: BenchModel | null
}

export interface BuildPlan {
  title: string
  summary: string
  final_result: string
  code: string
  safety: string[]
  parts: { name: string; quantity: number; why: string; user_has_it: boolean; size: string }[]
  part_guide: Record<string, string>
  model: BenchModel | null
  steps: BuildStep[]
}

export interface BuildCommit {
  id: string
  kind: 'start' | 'step'
  step: number | null
  message: string
  time: string // ISO
  images: string[]
  verdict?: Verdict
  model?: BenchModel | null
  guide?: Record<string, string>
  detected?: { name: string; quantity: number; where: string; scene_id: string }[]
  parent?: string
}

export interface Build {
  id: string
  mine?: boolean // false: someone else's build shared by link (only its owner can commit)
  owner_name?: string | null
  status: 'scanning' | 'planning' | 'checking' | 'modelling' | 'done' | 'error'
  stage: string
  error: string | null
  goal: string
  plan: BuildPlan | null
  commits: BuildCommit[]
}

export const startBuild = (inputs: { goal: string; have?: string; known?: string; photos?: string[] }) =>
  call<{ id: string }>('/api/build', { method: 'POST', headers: headers(true), body: JSON.stringify(inputs) })

export const getBuild = (id: string) => call<Build>(`/api/build/${encodeURIComponent(id)}`, { headers: headers() })

/** Photos of the bench after a step: the AI's verdict and a 3D model of what was photographed (10–60 s). */
export const commitStep = (id: string, step: number, photos: string[], note: string) =>
  call<BuildCommit>(`/api/build/${encodeURIComponent(id)}/commit`, {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ step, photos, note }),
  })

// --- Accounts (mcp-server/physical_studio/users.py) ---------------------------------------------------

export const signUp = (email: string, password: string, name: string) =>
  call<{ token: string; user: User }>('/api/auth/signup', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ email, password, name }),
  })

export const logIn = (email: string, password: string) =>
  call<{ token: string; user: User }>('/api/auth/login', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ email, password }),
  })

export const logOut = () => call<object>('/api/auth/logout', { method: 'POST', headers: headers() })

export interface SavedProject {
  design: string
  title: string
  prompt: string
  steps: number
  updated: number // seconds
}

export const listSaved = () => call<SavedProject[]>('/api/projects', { headers: headers() })

export const saveProject = (p: { design: string; title: string; prompt?: string; steps?: number }) =>
  call<SavedProject>('/api/projects', { method: 'POST', headers: headers(true), body: JSON.stringify(p) })

export const forgetSaved = (design: string) =>
  call<object>('/api/projects/forget', { method: 'POST', headers: headers(true), body: JSON.stringify({ design }) })
