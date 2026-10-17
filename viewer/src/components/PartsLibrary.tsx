// Screen 1 parts library panel: every part in parts/*.json with its body size and whether the numbers
// were measured or come from a datasheet. Clicking a card hands the part to the Describe page.
import { useEffect, useMemo, useState } from 'react'
import { listParts, type PartSummary } from '../api'
import './PartsLibrary.css'

const fmt = (mm: number) => String(Math.round(mm * 10) / 10)

export function PartsLibrary({ onPick }: { onPick?: (part: PartSummary) => void }) {
  const [parts, setParts] = useState<PartSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
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

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!parts || !q) return parts ?? []
    return parts.filter((p) => [p.name, p.id, p.category].some((s) => s.toLowerCase().includes(q)))
  }, [parts, query])

  const retry = () => {
    setError(null)
    setParts(null)
    setAttempt((n) => n + 1)
  }

  return (
    <aside className="parts-library" aria-label="Parts library">
      <div className="parts-head">
        <h2>Parts library</h2>
        {parts && <span className="parts-total">{parts.length}</span>}
      </div>
      <p className="parts-lede">Designs only use these parts, with their real dimensions.</p>
      <input
        className="parts-search"
        type="search"
        value={query}
        placeholder="Search by name, id or category"
        aria-label="Search parts"
        onChange={(e) => setQuery(e.target.value)}
      />
      {error ? (
        <div className="parts-error">
          <p>Couldn't load the parts: {error}</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      ) : !parts ? (
        <ul className="parts-list" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="parts-card parts-skeleton" />
          ))}
        </ul>
      ) : shown.length === 0 ? (
        <p className="parts-empty">{parts.length ? `No parts match “${query.trim()}”.` : 'The library is empty.'}</p>
      ) : (
        <ul className="parts-list">
          {shown.map((part) => (
            <li key={part.id}>
              <button
                type="button"
                className="parts-card"
                disabled={!onPick}
                title={onPick ? `Add ${part.name} to the prompt` : undefined}
                onClick={() => onPick?.(part)}
              >
                <span className="parts-name">{part.name}</span>
                <span className={`parts-badge${part.verified ? ' measured' : ''}`} title={part.source}>
                  {part.verified ? 'Measured' : 'Datasheet'}
                </span>
                <span className="parts-size">{part.body_size.map(fmt).join(' × ')} mm</span>
                <span className="parts-meta">
                  {part.category} · {part.id}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
