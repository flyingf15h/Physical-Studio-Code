// Client for the design backend (mcp-server/physical_studio/jobs.py, served by the MCP server's
// HTTP app; Caddy and the Vite dev server route /api/parts and /api/design* to it).

import { authToken, type User } from './auth'
import { reach } from './network'
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
  const res = await reach(url, init)
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
  next?: string // hardware builds: what to do now
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
  section?: string | null // hardware builds: the group this step belongs to ("Cart and drive motor")
  tools?: string[] // hardware builds: tools this step needs
  picture_view?: string // hardware builds: the angle of the step picture (iso, iso_right, iso_back, iso_left_back, below)
  picture_wires?: { id: string; points: [number, number][] }[] // hardware builds: each wire in the picture, in fractions of its width and height
  picture_close_up?: boolean // hardware builds: the picture zooms in on this step's parts
  // Hardware builds: the step's motion, `count` frames side by side in one PNG with the picture's camera
  // (the new parts on their way in, screws turning; with `seated`, the last frame has every part in and the
  // new wires still out).
  picture_frames?: { src: string; count: number; seated: boolean }
}

/** One end of a wire: the part and the pin label printed on it. */
export interface WireEnd {
  part: string
  pin: string
}

/** Hardware builds: what the page shows when a wire is clicked in the step picture or the 3D model. */
export interface WireInfo {
  name: string
  color: string
  from: WireEnd
  to: WireEnd
  length_mm: number | null
  inline?: string // a component spliced into the wire ("220 ohm resistor")
  ends: [number, number, number][] | null // where each end sits in the GLB (metres, +Y up)
}

export interface BuildPlan {
  kind?: 'cad' // a hardware build from the CAD design pipeline (bench/cad_guide.py); else a breadboard build
  title: string
  summary: string
  final_result: string
  code: string
  safety: string[]
  parts: { name: string; quantity: number; why: string; user_has_it: boolean; size: string }[]
  part_guide: Record<string, string>
  wires?: Record<string, WireInfo> // hardware builds: wire id -> its two ends
  pin_map?: PinMapBoard[] // hardware builds: every wired pin of each board, for the firmware
  model: BenchModel | null
  steps: BuildStep[]
  imported?: ImportedProject // builds made with "Import a project"
}

/** One board's wired pins: "pin 18 / SDA" -> ["Cart joint encoder SDA", "Left distance sensor SDA"]. */
export interface PinMapBoard {
  board: string
  pins: { pin: string; to: string[]; colour: string }[]
}

/** Where an imported build came from, and the project's own CAD files placed side by side in one model. */
export interface ImportedProject {
  url: string
  title: string
  model: BenchModel | null
  files: { name: string; url: string; note?: string }[]
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
  ready?: boolean // a ready-made guide: view-only, copyBuild() makes your own
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

/** "Import a project": a link to an existing project (a GitHub repository, or a Printables, Thingiverse or
 * Instructables page) becomes a build guide from what's there (bench/importer.py). */
export const importProject = (url: string) =>
  call<{ id: string }>('/api/build/import', { method: 'POST', headers: headers(true), body: JSON.stringify({ url }) })

export const getBuild = (id: string) => call<Build>(`/api/build/${encodeURIComponent(id)}`, { headers: headers() })

/** A "Parts I have" entry looked up in the parts library (bench routes.py, the planner's own lookup). */
export interface MatchedPart {
  id: string
  name: string
  category: PartSummary['category']
  size: string
  verified: boolean
}
export const matchParts = (items: string[]) =>
  call<{ items: { text: string; part: MatchedPart | null }[] }>('/api/build/match', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ items }),
  })

/** Your own copy of a finished build (a ready-made guide), to commit photos to. */
export const copyBuild = (id: string) =>
  call<{ id: string }>(`/api/build/${encodeURIComponent(id)}/copy`, { method: 'POST', headers: headers() })

/** Photos of the bench after a step: the AI's verdict and a 3D model of what was photographed (10–60 s). */
export const setBuildSummary = (id: string, summary: string) =>
  call<{ summary: string }>(`/api/build/${encodeURIComponent(id)}/summary`, {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ summary }),
  })

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

export const guestLogIn = () =>
  call<{ token: string; user: User }>('/api/auth/guest', { method: 'POST', headers: headers() })

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

// --- BOM uploads (mcp-server/physical_studio/boms.py): rows the library has are used as they are,
// the others are looked up online and added to your own parts.

export interface BomRow {
  name: string
  link: string
  price: string
  quantity: number
  status: 'looking' | 'in_library' | 'added' | 'failed'
  part_id?: string
  part_name?: string
  size?: string
  error?: string
}

export const uploadBom = (text: string) =>
  call<{ id: string }>('/api/bom', { method: 'POST', headers: headers(true), body: JSON.stringify({ text }) })

export const getBom = (id: string) =>
  call<{ id: string; status: 'working' | 'done'; rows: BomRow[] }>(`/api/bom/${encodeURIComponent(id)}`, { headers: headers() })
