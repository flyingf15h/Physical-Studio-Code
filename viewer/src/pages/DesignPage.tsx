// Screen 2 · the AI designs it. Polls the design job and shows its progress, previews and checks.
import { useEffect, useState } from 'react'
import { getDesign, type DesignJob, type JobEvent, type JobEventKind } from '../api'
import { DesignModel } from '../components/DesignModel'
import { ProgressHeader } from '../components/ProgressHeader'
import { designParams, navigate, withParams } from '../router'
import './DesignPage.css'

const POLL_MS = 1500

const PHASES: { kind: JobEventKind; todo: string }[] = [
  { kind: 'parts', todo: 'Finding parts' },
  { kind: 'place', todo: 'Placing parts' },
  { kind: 'case', todo: 'Building the case' },
  { kind: 'wire', todo: 'Wiring connections' },
  { kind: 'check', todo: 'Checking that everything fits' },
  { kind: 'steps', todo: 'Writing the assembly steps' },
]

function lastOf(events: JobEvent[], kind: JobEventKind) {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].kind === kind) return events[i]
  return undefined
}

export function DesignPage({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<DesignJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [shown, setShown] = useState<string | null>(null) // preview picked from the strip

  useEffect(() => {
    let stop = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const j = await getDesign(jobId)
        if (stop) return
        setJob(j)
        setError(null)
        if (j.status === 'done' || j.status === 'error') return
      } catch (e) {
        if (!stop) setError(e instanceof Error ? e.message : String(e))
      }
      timer = window.setTimeout(poll, POLL_MS)
    }
    void poll()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [jobId])

  const events = job?.events ?? []
  const finished = job?.status === 'done'
  const designer = job?.designer ?? 'The AI'
  // The phase in progress is the one after the furthest phase reached so far.
  const reached = PHASES.map((p) => !!lastOf(events, p.kind))
  const furthest = reached.lastIndexOf(true)
  const previews = events.filter((e) => e.kind === 'preview' && e.image)
  const fixes = events.filter((e) => e.kind === 'fix')
  const notes = events.filter((e) => e.kind === 'note').slice(-4)
  const image = shown ?? job?.preview ?? null
  const code = designParams().code
  const guide = job?.design ? withParams('/guide', { design: job.design, job: jobId, code }) : null

  const check = (label: string, value: { ok: boolean } | null | undefined, detail?: string) => (
    <li className={value == null ? 'pending' : value.ok ? 'ok' : 'bad'}>
      <span className="label">{label}</span>
      <span className="value">{value == null ? '…' : value.ok ? 'OK' : 'Needs a fix'}</span>
      {detail && <span className="detail">{detail}</span>}
    </li>
  )

  return (
    <div className="page">
      <ProgressHeader active={finished ? 3 : 2} job={jobId} design={job?.design} />
      <main className="design-page">
        <section className="design-left">
          <div className="ds-card prompt-card">
            <div className="eyebrow">Your prompt</div>
            <p>{job?.prompt ?? '…'}</p>
            {!!job?.attachments?.images.length && (
              <div className="prompt-images">
                {job.attachments.images.map((src, i) => (
                  <a key={src} href={src} target="_blank" rel="noreferrer">
                    <img src={src} alt={`Attached image ${i + 1}`} />
                  </a>
                ))}
              </div>
            )}
            {job?.attachments?.links.map((link) => (
              <p key={link.url} className="prompt-link">
                <a href={link.url} target="_blank" rel="noreferrer">
                  {link.url}
                </a>
                {link.error && <span> · couldn't read it ({link.error})</span>}
              </p>
            ))}
          </div>

          <div className="ds-card">
            <div className="row">
              <h2>
                {finished ? `${designer} designed it` : job?.status === 'error' ? 'Design stopped' : `${designer} is designing`}
              </h2>
              <span className={`badge ${job?.status ?? 'queued'}`}>
                {job?.status === 'running' ? 'working' : (job?.status ?? 'loading')}
              </span>
            </div>
            <ol className="phases">
              {PHASES.map((p, i) => {
                const ev = lastOf(events, p.kind)
                const state =
                  finished || (ev && i < furthest)
                    ? 'done'
                    : ev
                      ? 'active'
                      : i === furthest + 1 && job?.status === 'running'
                        ? 'active'
                        : 'todo'
                return (
                  <li key={p.kind} className={state}>
                    <span className="mark">{state === 'done' ? '✓' : state === 'active' ? '◐' : '○'}</span>
                    {ev?.text ?? p.todo}
                  </li>
                )
              })}
            </ol>
          </div>

          {fixes.map((f, i) => (
            <div key={i} className="ds-card fix-card">
              <div className="eyebrow">Fixed a problem</div>
              <p>{f.text.replace(/^Fixed a problem:\s*/, '').replace(/^./, (c) => c.toUpperCase())}</p>
            </div>
          ))}

          {notes.length > 0 && (
            <div className="ds-card notes">
              <div className="eyebrow">{designer}'s notes</div>
              {notes.map((n, i) => (
                <p key={i}>{n.text}</p>
              ))}
            </div>
          )}

          {(job?.error || error) && <div className="error-card">{job?.error ?? error}</div>}
        </section>

        <section className="design-right">
          <div className="ds-card preview-card">
            <div className="row">
              <h2>{job?.title ?? 'New design'}</h2>
              {guide && (
                <button className="primary" onClick={() => navigate(guide)}>
                  Open the assembly guide →
                </button>
              )}
            </div>
            <div className="preview">
              {job?.design && !shown ? (
                <DesignModel design={job.design} />
              ) : image ? (
                <img src={image} alt="Preview of the design" />
              ) : (
                <p className="muted">The 3D preview appears here as {designer} works.</p>
              )}
            </div>
            {(previews.length > 1 || (job?.design && previews.length > 0)) && (
              <div className="strip">
                {job?.design && (
                  <button className={shown ? 'model' : 'model on'} onClick={() => setShown(null)} title="Rotate the finished design">
                    3D
                  </button>
                )}
                {previews.map((p) => (
                  <button
                    key={p.image}
                    className={p.image === image ? 'on' : ''}
                    onClick={() => setShown(p.image!)}
                    title={p.text}
                  >
                    <img src={p.image} alt={p.text} />
                  </button>
                ))}
              </div>
            )}
          </div>
          <ul className="ds-card checks">
            {check(
              'Parts collide',
              job?.checks.interference ? { ok: job.checks.interference.ok } : null,
              job?.checks.interference && !job.checks.interference.ok
                ? `${job.checks.interference.problems} to fix`
                : undefined,
            )}
            {check('Ports reachable', job?.checks.clearance, job?.checks.clearance?.notes[0])}
            {check(
              'Fits the printer',
              job?.checks.printer,
              job?.checks.printer
                ? `${job.checks.printer.size_mm.map((v) => Math.round(v)).join(' × ')} mm`
                : undefined,
            )}
          </ul>
        </section>
      </main>
    </div>
  )
}
