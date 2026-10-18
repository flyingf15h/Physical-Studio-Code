// "Parts I have" on the Dashboard: each part you type (Enter or a comma) becomes its own chip, looked up
// in the parts library (POST /api/build/match, the same lookup the build planner uses). A matched chip
// shows the library part and its size; others say they're not in the library and still go to the planner.
// Typing suggests library parts by name.
import { useEffect, useMemo, useRef, useState } from 'react'
import { listParts, matchParts, type MatchedPart, type PartSummary } from '../api'
import './PartsInput.css'

const MAX_PARTS = 40

/** "Arduino Uno, 3 LEDs and a breadboard" -> ["Arduino Uno", "3 LEDs", "a breadboard"] */
function splitParts(text: string): string[] {
  return text
    .split(/[,;\n+]|\band\b/i)
    .map((s) => s.trim().replace(/^[-•.]+\s*/, ''))
    .filter(Boolean)
}

export function PartsInput({ parts, onChange }: { parts: string[]; onChange: (parts: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const [found, setFound] = useState<Record<string, MatchedPart | null>>({})
  const [library, setLibrary] = useState<PartSummary[]>([])
  const [focus, setFocus] = useState(-1) // highlighted suggestion
  const field = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listParts().then(setLibrary, () => setLibrary([]))
  }, [])

  // Look up chips we haven't looked up yet.
  useEffect(() => {
    const todo = parts.filter((p) => !(p in found))
    if (!todo.length) return
    let live = true
    matchParts(todo).then(
      ({ items }) => live && setFound((now) => ({ ...now, ...Object.fromEntries(items.map((i, k) => [todo[k], i.part])) })),
      () => live && setFound((now) => ({ ...now, ...Object.fromEntries(todo.map((t) => [t, null])) })),
    )
    return () => {
      live = false
    }
  }, [parts, found])

  const suggestions = useMemo(() => {
    const words = draft.toLowerCase().split(/\s+/).filter((w) => w.length > 1)
    if (!words.length) return []
    const score = (p: PartSummary) => words.filter((w) => `${p.name} ${p.id}`.toLowerCase().includes(w)).length
    return library
      .map((p) => ({ p, s: score(p) }))
      .filter(({ s, p }) => s === words.length && !parts.includes(p.name))
      .slice(0, 6)
      .map(({ p }) => p)
  }, [draft, library, parts])

  const add = (items: string[]) => {
    const next = [...parts]
    for (const item of items.map((i) => i.slice(0, 120))) if (item && !next.includes(item)) next.push(item)
    onChange(next.slice(0, MAX_PARTS))
    setDraft('')
    setFocus(-1)
  }
  const remove = (part: string) => onChange(parts.filter((p) => p !== part))

  return (
    <div className="parts-input" onClick={() => field.current?.focus()}>
      <div className="parts-input-head">
        <span className="parts-input-label">Parts I have</span>
        <span className="parts-input-hint">Optional. Press Enter or type a comma after each part.</span>
      </div>
      <ul className="parts-input-chips">
        {parts.map((part) => {
          const match = found[part]
          return (
            <li
              key={part}
              className={`parts-have-chip${match ? ' matched' : match === null ? ' unmatched' : ''}`}
              title={match ? `${match.name}${match.size ? ` · ${match.size}` : ''}` : match === null ? 'Not in the parts library; the planner still uses it' : 'Looking it up…'}
            >
              <span className="parts-have-text">{part}</span>
              <span className="parts-have-match">
                {match ? `✓ ${match.name}` : match === null ? 'Not in library' : 'Looking up…'}
                {match?.size ? <span className="parts-have-size"> · {match.size}</span> : null}
              </span>
              <button
                type="button"
                aria-label={`Remove ${part}`}
                onClick={(e) => {
                  e.stopPropagation()
                  remove(part)
                }}
              >
                ×
              </button>
            </li>
          )
        })}
        <li className="parts-input-field">
          <input
            ref={field}
            value={draft}
            maxLength={200}
            placeholder={parts.length ? 'Add another part…' : 'e.g. Arduino Uno, 3 LEDs, 220 Ω resistors, breadboard'}
            aria-label="Parts I have"
            onChange={(e) => {
              const text = e.target.value
              if (/[,;\n]/.test(text)) add(splitParts(text))
              else setDraft(text)
            }}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text')
              if (/[,;\n]/.test(text)) {
                e.preventDefault()
                add(splitParts(draft + text))
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown' && suggestions.length) {
                e.preventDefault()
                setFocus((focus + 1) % suggestions.length)
              } else if (e.key === 'ArrowUp' && suggestions.length) {
                e.preventDefault()
                setFocus((focus - 1 + suggestions.length) % suggestions.length)
              } else if (e.key === 'Enter') {
                e.preventDefault()
                if (focus >= 0 && suggestions[focus]) add([suggestions[focus].name])
                else if (draft.trim()) add(splitParts(draft))
              } else if (e.key === 'Backspace' && !draft && parts.length) {
                remove(parts[parts.length - 1])
              } else if (e.key === 'Escape') setFocus(-1)
            }}
            onBlur={() => {
              if (draft.trim()) add(splitParts(draft))
            }}
          />
          {suggestions.length > 0 && (
            <ul className="parts-input-suggest" role="listbox">
              {suggestions.map((p, i) => (
                <li
                  key={p.id}
                  role="option"
                  aria-selected={i === focus}
                  className={i === focus ? 'active' : ''}
                  onMouseDown={(e) => {
                    e.preventDefault() // keep focus in the field
                    add([p.name])
                  }}
                >
                  <span>{p.name}</span>
                  <span className="parts-input-suggest-size">{p.body_size.map((v) => +v.toFixed(1)).join(' × ')} mm</span>
                </li>
              ))}
            </ul>
          )}
        </li>
      </ul>
    </div>
  )
}
