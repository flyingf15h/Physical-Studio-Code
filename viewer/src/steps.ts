// Types for design.steps.json. Source of truth: schemas/steps.schema.json, docs/steps-format.md.
import { reach } from './network'

export type Vec3 = [number, number, number]

export interface PinRef {
  placement: string
  pin: string
}

export interface Placement {
  id: string
  kind: 'enclosure' | 'part' | 'fastener' | 'wire'
  part: string | null
  name: string
  position: Vec3
  rotation: Vec3
  color?: string
  pins?: { id: string; position: Vec3 }[] // parts: pin tips in the part frame, for drawing legs
  // wires only
  from?: PinRef
  to?: PinRef
  length_mm?: number
  inline?: string
}

export interface Motion {
  placement: string
  from_offset?: Vec3
  from_rotation?: Vec3
}

export interface Step {
  index: number
  title: string
  text: string
  add: string[]
  motion?: Motion[]
  tools?: { name: string; for?: string }[]
  callouts?: { text: string; target: string; at?: Vec3 }[]
  dimensions?: { from: Vec3; to: Vec3; label: string }[]
  check?: string
}

export interface StepsDoc {
  format: 'physical-studio-steps'
  version: 1
  title: string
  prompt?: string
  model: string
  units: 'mm'
  bounds?: { min: Vec3; max: Vec3 }
  placements: Placement[]
  steps: Step[]
}

export async function loadSteps(url: string): Promise<StepsDoc> {
  const res = await reach(url)
  if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`)
  const doc = (await res.json()) as StepsDoc
  if (doc.format !== 'physical-studio-steps') throw new Error(`${url} is not a Physical Studio steps file`)
  doc.steps.sort((a, b) => a.index - b.index)
  return doc
}

/** Step position (0-based) in which each placement first appears. */
export function addedAt(doc: StepsDoc): Map<string, number> {
  const map = new Map<string, number>()
  doc.steps.forEach((s, i) => s.add.forEach((id) => map.has(id) || map.set(id, i)))
  return map
}

/** The motion entry that brings each placement in, used for animation and the exploded view. */
export function motions(doc: StepsDoc): Map<string, Motion> {
  const map = new Map<string, Motion>()
  for (const s of doc.steps) for (const m of s.motion ?? []) map.set(m.placement, m)
  return map
}
