// Screen 1 parts library panel: every part in parts/*.json with its body size and whether the numbers
// were measured or come from a datasheet. Clicking a card hands the part to the Describe page.
// A logged-in user's own parts (from their uploaded BOMs, `mine: true`) come first.
import { useEffect, useMemo, useState } from 'react'
import { listParts, type PartSummary } from '../api'
import { authToken, useUser } from '../auth'
import { BomUpload } from './BomUpload'
import { searchParts } from '../partSearch'
import './PartsLibrary.css'

const fmt = (mm: number) => String(Math.round(mm * 10) / 10)

type Category = PartSummary['category']
const CATEGORIES: Category[] = ['board', 'input', 'output', 'misc', 'fastener']

type LibraryPart = PartSummary & { mine?: boolean }

/** /api/parts with the session token, so the server also sends the user's own parts. */
async function listLibrary(): Promise<LibraryPart[]> {
  const token = authToken()
  if (!token) return listParts()
  const res = await fetch('/api/parts', { headers: { Authorization: `Bearer ${token}` } })
  const body = await res.json().catch(() => null)
  if (res.status === 401) return listParts() // stale session: show the shared library
  if (!res.ok) throw new Error(body?.error ?? `/api/parts: ${res.status}`)
  if (body === null) throw new Error("/api/parts: the server didn't answer with JSON")
  return body as LibraryPart[]
}

export function PartsLibrary({ onPick }: { onPick?: (part: PartSummary) => void }) {
  const user = useUser()
  const userId = user?.id ?? null
  const [parts, setParts] = useState<LibraryPart[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<Category | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    let live = true
    listLibrary()
      .then((list) => {
        if (!live) return
        // the user's own parts first, the rest in the server's order
        setParts([...list.filter((p) => p.mine), ...list.filter((p) => !p.mine)])
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      live = false
    }
  }, [attempt, userId])

  // after a BOM upload finishes: fetch again without blanking the list
  const refresh = () => {
    setError(null)
    setAttempt((n) => n + 1)
  }

  const counts = useMemo(() => {
    const c: Partial<Record<Category, number>> = {}
    for (const p of parts ?? []) c[p.category] = (c[p.category] ?? 0) + 1
    return c
  }, [parts])

  const shown = useMemo(() => {
    const inCategory = (parts ?? []).filter((p) => !category || p.category === category)
    // Typing ranks the likeliest part first ("le" -> LED 5 mm); see partSearch.ts.
    return query.trim() ? searchParts(inCategory, query, inCategory.length) : inCategory
  }, [parts, query, category])

  const retry = () => {
    setError(null)
    setParts(null)
    setAttempt((n) => n + 1)
  }

  const filtered = query.trim() || category
  const chip = (value: Category | null, label: string, count?: number) => (
    <button
      key={label}
      type="button"
      className={`parts-chip${category === value ? ' active' : ''}`}
      aria-pressed={category === value}
      onClick={() => setCategory(value)}
    >
      {label}
      {count !== undefined && <span className="parts-chip-count">{count}</span>}
    </button>
  )

  return (
    <section className="parts-library" aria-label="Parts library">
      <div className="parts-head">
        <h2>Parts library</h2>
        {parts && <span className="parts-total">{parts.length}</span>}
        <span className="parts-lede">Designs only use these parts, with their real dimensions.</span>
        <button
          type="button"
          className={`parts-upload${uploading ? ' active' : ''}`}
          aria-expanded={uploading}
          onClick={() => setUploading((u) => !u)}
        >
          Upload BOM
        </button>
      </div>
      {uploading && <BomUpload onDone={refresh} onClose={() => setUploading(false)} />}
      <div className="parts-tools">
        <input
          className="parts-search"
          type="search"
          value={query}
          placeholder="Search by name, id or category"
          aria-label="Search parts"
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="parts-chips" role="group" aria-label="Filter by category">
          {chip(null, 'All', parts?.length)}
          {CATEGORIES.map((c) => chip(c, c, parts ? (counts[c] ?? 0) : undefined))}
        </div>
      </div>
      {error ? (
        <div className="parts-error">
          <p>Couldn't load the parts: {error}</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      ) : !parts ? (
        <ul className="parts-list" aria-busy="true">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <li key={i} className="parts-card parts-skeleton" />
          ))}
        </ul>
      ) : shown.length === 0 ? (
        <p className="parts-empty">
          {!parts.length
            ? 'The library is empty.'
            : query.trim()
              ? `No ${category ?? ''} parts match “${query.trim()}”.`
              : `No ${category} parts yet.`}
        </p>
      ) : (
        <ul className="parts-list" aria-label={filtered ? `${shown.length} of ${parts.length} parts` : undefined}>
          {shown.map((part) => (
            <li key={part.id}>
              <button
                type="button"
                className="parts-card"
                disabled={!onPick}
                title={`${part.name} (${part.category} · ${part.id})${onPick ? ' — click to add it to the prompt' : ''}`}
                onClick={() => onPick?.(part)}
              >
                <span className="parts-name">{part.name}</span>
                {part.mine ? (
                  <span
                    className="parts-badge mine"
                    title={`From your BOM${part.source ? `: ${part.source}` : ''}`}
                    aria-label="From your BOM"
                  >
                    Your BOM
                  </span>
                ) : (
                  <span
                    className={`parts-badge${part.verified ? ' measured' : ''}`}
                    title={`${part.verified ? 'Measured' : 'Datasheet'}${part.source ? `: ${part.source}` : ''}`}
                    aria-label={part.verified ? 'Measured' : 'Datasheet'}
                  >
                    {part.verified ? 'M' : 'DS'}
                  </span>
                )}
                <span className="parts-size">{part.body_size.map(fmt).join(' × ')} mm</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
