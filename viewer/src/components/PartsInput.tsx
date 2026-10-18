// "Parts I have" on the Dashboard: each part you type (Enter or a comma) becomes its own chip, looked up
// in the parts library (POST /api/build/match, the same lookup the build planner uses). A matched chip
// shows the library part and its size; others say they're not in the library and still go to the planner.
// Typing suggests library parts as you go ("le" -> LED 5 mm first; partSearch.ts) and Enter takes the
// highlighted one, keeping a quantity typed before it ("3 le" -> "3 × LED 5 mm"). A part that isn't in the
// library can be added with your own details (type, size, pins), which go to the planner with its name.
import { useEffect, useMemo, useRef, useState } from 'react'
import { listParts, matchParts, type MatchedPart, type PartSummary } from '../api'
import { searchParts, splitCount } from '../partSearch'
import './PartsInput.css'

const MAX_PARTS = 40
const CUSTOM = /\s\(your part: (.*)\)$/ // "Hall sensor (your part: sensor, 10 × 4 × 3 mm, pins VCC GND OUT)"
const KINDS = ['board', 'sensor or input', 'output (light, sound, motor)', 'power', 'mechanical', 'other']

/** "Arduino Uno, 3 LEDs and a breadboard" -> ["Arduino Uno", "3 LEDs", "a breadboard"] */
function splitParts(text: string): string[] {
  return text
    .split(/[,;\n+]|\band\b/i)
    .map((s) => s.trim().replace(/^[-•.]+\s*/, ''))
    .filter(Boolean)
}

interface CustomDraft {
  name: string
  count: string
  kind: string
  size: [string, string, string]
  pins: string
  notes: string
}

/** A part that isn't in the library, described by the user. */
function CustomPartForm({ start, onSave, onCancel }: { start: string; onSave: (text: string) => void; onCancel: () => void }) {
  const first = splitCount(start)
  const [d, setD] = useState<CustomDraft>({ name: first.text, count: first.count, kind: KINDS[1], size: ['', '', ''], pins: '', notes: '' })
  const set = (patch: Partial<CustomDraft>) => setD((now) => ({ ...now, ...patch }))
  const size = d.size.every((v) => +v > 0) ? `${d.size.map((v) => +v).join(' × ')} mm` : ''
  const save = () => {
    const name = d.name.trim()
    if (!name) return
    const bits = [d.kind, size, d.pins.trim() && `pins ${d.pins.trim()}`, d.notes.trim()].filter(Boolean)
    onSave(`${d.count ? `${d.count} × ` : ''}${name} (your part: ${bits.join(', ')})`.slice(0, 300))
  }
  return (
    <form
      className="custom-part"
      onClick={(e) => e.stopPropagation()}
      onSubmit={(e) => {
        e.preventDefault()
        save()
      }}
    >
      <div className="custom-part-head">
        <strong>Add your own part</strong>
        <span className="muted">Not in the library? Describe it and the planner uses your numbers.</span>
      </div>
      <div className="custom-part-grid">
        <label className="wide">
          Name
          <input autoFocus value={d.name} maxLength={80} placeholder="e.g. A3144 hall effect sensor" onChange={(e) => set({ name: e.target.value })} />
        </label>
        <label>
          How many
          <input inputMode="numeric" value={d.count} maxLength={3} placeholder="1" onChange={(e) => set({ count: e.target.value.replace(/\D/g, '') })} />
        </label>
        <label>
          Type
          <select value={d.kind} onChange={(e) => set({ kind: e.target.value })}>
            {KINDS.map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
        <fieldset className="wide">
          <legend>Size in mm (length × width × height, optional)</legend>
          {d.size.map((v, i) => (
            <input
              key={i}
              inputMode="decimal"
              value={v}
              maxLength={6}
              aria-label={['Length', 'Width', 'Height'][i]}
              placeholder={['L', 'W', 'H'][i]}
              onChange={(e) => {
                const size = [...d.size] as CustomDraft['size']
                size[i] = e.target.value.replace(/[^\d.]/g, '')
                set({ size })
              }}
            />
          ))}
        </fieldset>
        <label className="wide">
          Pins (optional)
          <input value={d.pins} maxLength={120} placeholder="e.g. VCC, GND, OUT" onChange={(e) => set({ pins: e.target.value })} />
        </label>
        <label className="wide">
          Anything else (optional)
          <input value={d.notes} maxLength={120} placeholder="e.g. 5 V, output goes low near a magnet" onChange={(e) => set({ notes: e.target.value })} />
        </label>
      </div>
      <div className="custom-part-actions">
        <button type="button" className="ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={!d.name.trim()}>
          Add part
        </button>
      </div>
    </form>
  )
}

export function PartsInput({ parts, onChange }: { parts: string[]; onChange: (parts: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const [found, setFound] = useState<Record<string, MatchedPart | null>>({})
  const [library, setLibrary] = useState<PartSummary[]>([])
  const [focus, setFocus] = useState(0) // highlighted suggestion; the best match until you move
  const [custom, setCustom] = useState<string | null>(null) // the custom-part form, started from this text
  const field = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listParts().then(setLibrary, () => setLibrary([]))
  }, [])

  // Look up chips we haven't looked up yet (your own parts aren't in the library).
  useEffect(() => {
    const todo = parts.filter((p) => !(p in found) && !CUSTOM.test(p))
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

  const suggestions = useMemo(
    () => searchParts(library, draft).filter((p) => !parts.some((have) => have === p.name || have.endsWith(`× ${p.name}`))),
    [draft, library, parts],
  )
  // The last row of the list: add what's typed as your own part.
  const rows = draft.trim() ? suggestions.length + 1 : 0
  const active = Math.min(focus, Math.max(rows - 1, 0))

  const add = (items: string[]) => {
    const next = [...parts]
    for (const item of items.map((i) => i.slice(0, 300))) if (item && !next.includes(item)) next.push(item)
    onChange(next.slice(0, MAX_PARTS))
    setDraft('')
    setFocus(0)
  }
  const pick = (p: PartSummary) => {
    const { count } = splitCount(draft)
    add([count && count !== '1' ? `${count} × ${p.name}` : p.name])
  }
  const remove = (part: string) => onChange(parts.filter((p) => p !== part))
  const choose = (row: number) => {
    if (row < suggestions.length) pick(suggestions[row])
    else {
      setCustom(draft)
      setDraft('')
    }
  }

  return (
    <div className="parts-input" onClick={() => field.current?.focus()}>
      <div className="parts-input-head">
        <span className="parts-input-label">Parts I have</span>
        <span className="parts-input-hint">Optional. Start typing to pick from the library, or add your own part.</span>
      </div>
      <ul className="parts-input-chips">
        {parts.map((part) => {
          const own = part.match(CUSTOM)
          const match = own ? undefined : found[part]
          const name = own ? part.replace(CUSTOM, '') : part
          return (
            <li
              key={part}
              className={`parts-have-chip${own ? ' custom' : match ? ' matched' : match === null ? ' unmatched' : ''}`}
              title={
                own
                  ? `Your part: ${own[1]}`
                  : match
                    ? `${match.name}${match.size ? ` · ${match.size}` : ''}`
                    : match === null
                      ? 'Not in the parts library; the planner still uses it'
                      : 'Looking it up…'
              }
            >
              <span className="parts-have-text">{name}</span>
              <span className="parts-have-match">
                {own ? `Your part · ${own[1]}` : match ? `✓ ${match.name}` : match === null ? 'Not in library' : 'Looking up…'}
                {match?.size ? <span className="parts-have-size"> · {match.size}</span> : null}
              </span>
              <button
                type="button"
                aria-label={`Remove ${name}`}
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
            placeholder={parts.length ? 'Add another part…' : 'Start typing: led, button, servo, Arduino…'}
            aria-label="Parts I have"
            aria-autocomplete="list"
            aria-expanded={rows > 0}
            onChange={(e) => {
              const text = e.target.value
              if (/[,;\n]/.test(text)) add(splitParts(text))
              else {
                setDraft(text)
                setFocus(0)
              }
            }}
            onPaste={(e) => {
              const text = e.clipboardData.getData('text')
              if (/[,;\n]/.test(text)) {
                e.preventDefault()
                add(splitParts(draft + text))
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown' && rows) {
                e.preventDefault()
                setFocus((active + 1) % rows)
              } else if (e.key === 'ArrowUp' && rows) {
                e.preventDefault()
                setFocus((active - 1 + rows) % rows)
              } else if ((e.key === 'Enter' || e.key === 'Tab') && rows && (suggestions.length || e.key === 'Enter')) {
                e.preventDefault()
                if (suggestions.length || active < rows - 1) choose(active)
                else add(splitParts(draft)) // nothing in the library matches: keep what was typed
              } else if (e.key === 'Enter') {
                e.preventDefault()
              } else if (e.key === 'Backspace' && !draft && parts.length) {
                remove(parts[parts.length - 1])
              } else if (e.key === 'Escape') {
                if (draft) add(splitParts(draft))
              }
            }}
            onBlur={() => {
              if (draft.trim()) add(splitParts(draft))
            }}
          />
          {rows > 0 && (
            <ul className="parts-input-suggest" role="listbox">
              {suggestions.map((p, i) => (
                <li
                  key={p.id}
                  role="option"
                  aria-selected={i === active}
                  className={i === active ? 'active' : ''}
                  onMouseEnter={() => setFocus(i)}
                  onMouseDown={(e) => {
                    e.preventDefault() // keep focus in the field
                    pick(p)
                  }}
                >
                  <span>
                    {p.name}
                    {p.mine && <span className="parts-input-mine">Your BOM</span>}
                  </span>
                  <span className="parts-input-suggest-size">{p.body_size.map((v) => +v.toFixed(1)).join(' × ')} mm</span>
                </li>
              ))}
              <li
                role="option"
                aria-selected={active === rows - 1}
                className={`parts-input-own${active === rows - 1 ? ' active' : ''}`}
                onMouseEnter={() => setFocus(rows - 1)}
                onMouseDown={(e) => {
                  e.preventDefault()
                  choose(rows - 1)
                }}
              >
                <span>
                  + Add “{splitCount(draft).text}” as your own part{suggestions.length ? '' : ' (not in the library)'}
                </span>
                <span className="parts-input-suggest-size">enter type, size, pins</span>
              </li>
            </ul>
          )}
        </li>
      </ul>
      {custom !== null && (
        <CustomPartForm
          start={custom}
          onCancel={() => setCustom(null)}
          onSave={(text) => {
            add([text])
            setCustom(null)
          }}
        />
      )}
    </div>
  )
}
