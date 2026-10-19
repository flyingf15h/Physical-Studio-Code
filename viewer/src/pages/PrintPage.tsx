// Screen 5 · Print and share. Mockup: docs/product-vision.html.
// Reads ?design=out/<id>: <design>/design.steps.json (its `print` block has sizes, grams, minutes and
// file names), <design>/design-base.stl, design-lid.stl, design.step.
import { useEffect, useState } from 'react'
import { DesignModel } from '../components/DesignModel'
import { ProgressHeader } from '../components/ProgressHeader'
import { designParams, navigate, withParams } from '../router'
import { loadSteps, type Placement, type StepsDoc } from '../steps'
import './DesignPage.css'
import './PrintPage.css'

/** The `print` block export.py writes when the design has a case (docs/steps-format.md). */
interface PrintInfo {
  size_mm: [number, number, number]
  material?: string
  pieces: { id: string; name: string; file: string; grams: number; minutes: number }[]
  total_grams: number
  total_minutes: number
  step_file?: string
}

type PrintDoc = StepsDoc & { print?: PrintInfo }

function hours(minutes: number) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h ? (m ? `~${h} h ${m} min` : `~${h} h`) : `~${m} min`
}

interface PartRow {
  label: string
  detail?: string
  qty: number
}

/** Parts and screws grouped by library part, wires counted together. The printed case is in Case files. */
function partsList(doc: StepsDoc): PartRow[] {
  const groups = new Map<string, Placement[]>()
  for (const p of doc.placements) {
    if (p.kind !== 'part' && p.kind !== 'fastener') continue
    const key = p.part ?? p.name
    groups.set(key, [...(groups.get(key) ?? []), p])
  }
  // Three led-5mm placements named Red, Yellow and Green LED become one row: "Red LED, Yellow LED, Green LED" × 3.
  const rows: PartRow[] = [...groups.values()].map((ps) => ({
    label: [...new Set(ps.map((p) => p.name))].join(', '),
    qty: ps.length,
  }))
  const wires = doc.placements.filter((p) => p.kind === 'wire')
  if (wires.length) {
    const mm = wires.reduce((sum, w) => sum + (w.length_mm ?? 0), 0)
    rows.push({ label: 'Jumper wires', detail: mm ? `about ${Math.ceil(mm / 10)} cm in all` : undefined, qty: wires.length })
  }
  return rows
}

function toolsList(doc: StepsDoc): string[] {
  const names = doc.steps.flatMap((s) => (s.tools ?? []).map((t) => t.name))
  return [...new Set(names)].filter((n) => !/^hands only$/i.test(n))
}

/** What undoing one placement looks like, for the take-apart guide. */
function undo(p: Placement) {
  if (p.kind === 'wire') return `Unplug: ${p.name.replace(/^Wire /, '')}`
  if (p.kind === 'fastener') return `Unscrew the ${p.name}`
  if (p.kind === 'enclosure') return `Lift off the ${p.name.toLowerCase()}`
  return `Take out the ${p.name}`
}

export function PrintPage() {
  const { design, job, code } = designParams()
  const [doc, setDoc] = useState<PrintDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const base = design?.replace(/\/$/, '') ?? null

  useEffect(() => {
    if (!base) return
    let stop = false
    loadSteps(`/${base}/design.steps.json?t=${Date.now()}`).then(
      (d) => !stop && setDoc(d as PrintDoc),
      (e) => !stop && setError(e instanceof Error ? e.message : String(e)),
    )
    return () => {
      stop = true
    }
  }, [base])

  const guidePath = withParams('/guide', { design: base, job, code })
  const shareUrl = `${location.origin}${withParams('/guide', { design: base, code })}`
  const print = doc?.print
  const byId = new Map(doc?.placements.map((p) => [p.id, p]))

  const copy = () => {
    void navigator.clipboard?.writeText(shareUrl).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  return (
    <div className="page">
      <ProgressHeader active={5} />
      <main className="print-page">
        <div className="print-head">
          <div className="eyebrow">{doc?.title ?? (base ? 'Loading…' : 'No design')}</div>
          <h1>Print it, then share it</h1>
        </div>

        {!base && (
          <p className="print-error">
            No design picked. Open one from{' '}
            <a
              href="/projects"
              onClick={(e) => {
                e.preventDefault()
                navigate(withParams('/projects', { code }))
              }}
            >
              Your projects
            </a>
            .
          </p>
        )}
        {error && <p className="print-error">Couldn't load this design: {error}</p>}

        {doc && base && (
          <>
            <div className="print-grid">
              <section className="print-card" aria-label="Print files">
                <h2>Case files</h2>
                <DesignModel design={base} />
                {print ? (
                  <>
                    <ul className="print-facts">
                      <li>
                        <span>Size</span>
                        <span className="mono">{print.size_mm.map((n) => Math.round(n)).join(' × ')} mm</span>
                      </li>
                      <li>
                        <span>Print time</span>
                        <span className="mono">{hours(print.total_minutes)}</span>
                      </li>
                      <li>
                        <span>Filament</span>
                        <span className="mono">
                          {Math.round(print.total_grams)} g{print.material ? ` ${print.material}` : ''}
                        </span>
                      </li>
                    </ul>
                    <div className="print-downloads">
                      {print.pieces.map((p) => (
                        <a key={p.id} className="print-primary" href={`/${base}/${p.file}`} download={p.file}>
                          Download {p.name.toLowerCase()} STL
                          <small>
                            {Math.round(p.grams)} g · {hours(p.minutes)}
                          </small>
                        </a>
                      ))}
                      {print.step_file && (
                        <a className="print-secondary" href={`/${base}/${print.step_file}`} download={print.step_file}>
                          Download STEP (for CAD)
                        </a>
                      )}
                    </div>
                    <p className="print-note">Times and grams are rough estimates; your slicer has the real numbers.</p>
                  </>
                ) : (
                  <p className="print-note">This design has no printed case, so there is nothing to print.</p>
                )}
              </section>

              <section className="print-card" aria-label="Parts list">
                <h2>Parts list</h2>
                <table className="print-parts">
                  <thead>
                    <tr>
                      <th>Part</th>
                      <th>Qty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {partsList(doc).map((r) => (
                      <tr key={r.label}>
                        <td>
                          {r.label}
                          {r.detail && <small>{r.detail}</small>}
                        </td>
                        <td className="mono">{r.qty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {toolsList(doc).length > 0 && (
                  <>
                    <div className="print-sub">Tools</div>
                    <div className="print-chips">
                      {toolsList(doc).map((t) => (
                        <span key={t}>{t}</span>
                      ))}
                    </div>
                  </>
                )}
              </section>

              <section className="print-card" aria-label="Share">
                <h2>Share the guide</h2>
                <p className="print-note">Anyone with the link can follow the animated steps.</p>
                <label htmlFor="print-share" className="print-sub">
                  Guide link
                </label>
                <input id="print-share" type="text" readOnly value={shareUrl} onFocus={(e) => e.target.select()} />
                <button type="button" className="print-secondary" onClick={copy}>
                  {copied ? 'Link copied' : 'Copy link'}
                </button>
                <a
                  className="print-secondary"
                  href={guidePath}
                  onClick={(e) => {
                    e.preventDefault()
                    navigate(guidePath)
                  }}
                >
                  Open the guide
                </a>
                <a className="print-takeapart-link" href="#take-apart">
                  <strong>Take-apart guide</strong>
                  <span>The same steps in reverse, for repair and recycling.</span>
                </a>
              </section>
            </div>

            <section id="take-apart" className="print-card print-takeapart" aria-label="Take-apart guide">
              <h2>Take-apart guide</h2>
              <p className="print-note">
                Unplug the power first. Then work from the top down: each step undoes one assembly step, so parts come
                out whole and can be reused, repaired or recycled.
              </p>
              <ol>
                {[...doc.steps].reverse().map((s, i) => {
                  const parts = [...s.add]
                    .reverse()
                    .map((id) => byId.get(id))
                    .filter((p): p is Placement => !!p)
                  const tools = (s.tools ?? []).filter((t) => !/^hands only$/i.test(t.name))
                  return (
                    <li key={s.index}>
                      <div className="print-step-title">
                        <span className="num">{i + 1}</span>
                        Undo “{s.title}”
                      </div>
                      {parts.length > 0 && (
                        <ul>
                          {parts.map((p) => (
                            <li key={p.id}>{undo(p)}</li>
                          ))}
                        </ul>
                      )}
                      {tools.length > 0 && <small>Tools: {tools.map((t) => t.name).join(', ')}</small>}
                    </li>
                  )
                })}
              </ol>
            </section>
          </>
        )}
      </main>
    </div>
  )
}
