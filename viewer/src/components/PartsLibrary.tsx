// Screen 1 parts library panel: every part in parts/*.json with its body size and whether the numbers
// were measured or come from a datasheet. Clicking a card hands the part to the Describe page.
import { useEffect, useMemo, useState } from 'react'
import { listParts, type PartSummary } from '../api'
import './PartsLibrary.css'

const fmt = (mm: number) => String(Math.round(mm * 10) / 10)

type Category = PartSummary['category']
const CATEGORIES: Category[] = ['board', 'input', 'output', 'misc', 'fastener']

export function PartsLibrary({ onPick }: { onPick?: (part: PartSummary) => void }) {
  const [parts, setParts] = useState<PartSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<Category | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    listParts()
      .then((list) => live && setParts(list))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      live = false
    }
  }, [attempt])

  const counts = useMemo(() => {
    const c: Partial<Record<Category, number>> = {}
    for (const p of parts ?? []) c[p.category] = (c[p.category] ?? 0) + 1
    return c
  }, [parts])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (parts ?? []).filter(
      (p) =>
        (!category || p.category === category) &&
        (!q || [p.name, p.id, p.category].some((s) => s.toLowerCase().includes(q))),
    )
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
      </div>
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
                <span
                  className={`parts-badge${part.verified ? ' measured' : ''}`}
                  title={`${part.verified ? 'Measured' : 'Datasheet'}${part.source ? `: ${part.source}` : ''}`}
                  aria-label={part.verified ? 'Measured' : 'Datasheet'}
                >
                  {part.verified ? 'M' : 'DS'}
                </span>
                <span className="parts-size">{part.body_size.map(fmt).join(' × ')} mm</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
