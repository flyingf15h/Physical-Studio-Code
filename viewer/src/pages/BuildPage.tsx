// A breadboard build (/build/<id>): Senna's Build helper flow in the main site's layout. While the
// server plans it shows the stages; then the guide: your bench now (commit #0) and the parts you
// need, one step at a time (numbered-hole picture, check line, a 3D model of the bench after the
// step, and an optional photo commit the AI checks), the finished build, and the Commits tab.
import { useEffect, useRef, useState } from 'react'
import { commitStep, getBuild, type Build, type BuildCommit, type BuildPlan, type Verdict } from '../api'
import { BenchModel } from '../components/BenchModel'
import { ProgressHeader } from '../components/ProgressHeader'
import { ShareButton } from '../components/ShareButton'
import { shrink } from '../images'
import { rememberProject } from '../projects'
import './BuildPage.css'

const POLL_MS = 2500
const MAX_PHOTOS = 10
const STAGES: { status: Build['status']; label: string }[] = [
  { status: 'scanning', label: 'Looking at your bench photos' },
  { status: 'planning', label: 'Choosing the parts you still need and writing your steps' },
  { status: 'checking', label: 'Checking the circuit and fixing what is wrong' },
  { status: 'modelling', label: 'Building a 3D model for every step' },
]

function VerdictCard({ verdict, image }: { verdict: Verdict; image?: string }) {
  const tone = { done: 'ok', problem: 'bad', in_progress: 'wait', unclear: 'warn', error: 'warn' }[verdict.status]
  const head = {
    done: 'Looks right.',
    problem: verdict.problem || 'Something is wrong.',
    in_progress: 'Not finished yet.',
    unclear: "Can't tell from these photos.",
    error: 'The check failed.',
  }[verdict.status]
  return (
    <div className={`verdict ${tone}`}>
      {image && <img src={image} alt="Your photo" />}
      <div>
        <strong>{head}</strong> {verdict.status !== 'error' && verdict.observation}
        {verdict.status === 'problem' && verdict.fix && (
          <p className="verdict-fix">
            <span>How to fix it</span> {verdict.fix}
          </p>
        )}
        {verdict.status === 'unclear' && (
          <p className="verdict-fix">Take a sharper photo from straight above, close enough to read the row numbers.</p>
        )}
        {verdict.status === 'error' && (
          <p className="verdict-fix">{verdict.problem || 'Wait a moment and commit again.'}</p>
        )}
      </div>
    </div>
  )
}

function CommitBox({ build, step, onCommit }: { build: Build; step: number; onCommit: (c: BuildCommit) => void }) {
  const [photos, setPhotos] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const add = async (files: FileList | null) => {
    const picked = [...(files ?? [])].filter((f) => f.type.startsWith('image/')).slice(0, MAX_PHOTOS - photos.length)
    try {
      const shrunk = await Promise.all(picked.map(shrink))
      setPhotos((now) => [...now, ...shrunk].slice(0, MAX_PHOTOS))
    } catch {
      setError("Couldn't read that photo.")
    }
  }
  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      onCommit(await commitStep(build.id, step, photos, note.trim()))
      setPhotos([])
      setNote('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="commit-box">
      <h3>Commit this step</h3>
      <p className="muted">
        Take a photo of your bench after this step, from straight above. The AI checks it against the step and builds a
        3D model of what you built. It shows up in the Commits tab.
      </p>
      <div className="commit-row">
        <button
          type="button"
          className="tool"
          onClick={() => picker.current?.click()}
          disabled={busy || photos.length >= MAX_PHOTOS}
        >
          Add photos
        </button>
        <input
          ref={picker}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          hidden
          onChange={(e) => {
            void add(e.target.files)
            e.target.value = ''
          }}
        />
        <input
          className="commit-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Message or question (optional), e.g. Is the red LED the right way round?"
          aria-label="Commit message"
        />
        <button type="button" className="primary" disabled={busy || !photos.length} onClick={() => void send()}>
          {busy ? 'Checking…' : 'Commit and check'}
        </button>
      </div>
      {photos.length > 0 && (
        <ul className="commit-thumbs">
          {photos.map((src, i) => (
            <li key={src.slice(-24) + i}>
              <img src={src} alt={`Photo ${i + 1}`} />
              <button
                type="button"
                aria-label={`Remove photo ${i + 1}`}
                onClick={() => setPhotos(photos.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {busy && (
        <p className="muted">Checking your photos against this step and building a 3D model (up to a minute)…</p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}

function Overview({ build, plan }: { build: Build; plan: BuildPlan }) {
  const start = build.commits.find((c) => c.kind === 'start')
  return (
    <div className="build-section">
      <p className="lede">{plan.summary}</p>
      <h2>Your bench now (commit #0)</h2>
      {start?.model ? (
        <BenchModel model={start.model} guide={start.guide} />
      ) : (
        <p className="muted">
          {start?.images.length ? 'Nothing is plugged in yet in your photos, so' : 'No bench photos, so'} the steps
          start from an empty breadboard.
        </p>
      )}
      {!!start?.detected?.length && (
        <>
          <h3>Parts spotted in your photos</h3>
          <table className="build-table">
            <thead>
              <tr>
                <th>Part</th>
                <th>Qty</th>
                <th>Where</th>
              </tr>
            </thead>
            <tbody>
              {start.detected.map((d, i) => (
                <tr key={i}>
                  <td>{d.name}</td>
                  <td>{d.quantity}</td>
                  <td>{d.where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <h2>Parts you need</h2>
      <table className="build-table">
        <thead>
          <tr>
            <th>Part</th>
            <th>Qty</th>
            <th>Size</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {plan.parts.map((p, i) => (
            <tr key={i}>
              <td>
                {p.name} {!p.user_has_it && <span className="pill">added</span>}
              </td>
              <td>{p.quantity}</td>
              <td className="muted">{p.size}</td>
              <td>{p.why}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StepView({
  build,
  plan,
  index,
  onCommit,
}: {
  build: Build
  plan: BuildPlan
  index: number
  onCommit: (c: BuildCommit) => void
}) {
  const s = plan.steps[index]
  const mine = build.commits.filter((c) => c.kind === 'step' && c.step === index)
  const last = mine[mine.length - 1]
  return (
    <div className="build-section">
      <div className="eyebrow">
        Step {index + 1} of {plan.steps.length}
      </div>
      <h2 className="step-title">{s.title}</h2>
      {s.picture && <img className="step-picture" src={s.picture} alt={`Step ${index + 1}: where each part goes`} />}
      <p className="step-text">{s.instruction}</p>
      {s.markers.length > 0 && (
        <ol className="markers">
          {s.markers.map(([n, what, where, hole]) => (
            <li key={n}>
              <span className="marker-n">{n}</span>
              <span>
                <strong>{what}</strong> → {where} <code>{hole}</code>
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="check">
        <span>Camera check</span> {s.check}
      </p>
      {s.model && (
        <>
          <h3>Your bench after step {index + 1}</h3>
          <BenchModel model={s.model} guide={plan.part_guide} highlight={s.model.new ?? s.part_ids} />
        </>
      )}
      {build.mine === false ? (
        <p className="muted shared-note">
          {build.owner_name ? `${build.owner_name} shared this build with you.` : 'This build was shared with you.'}{' '}
          Only the person who started it can commit photos to it.
        </p>
      ) : (
        <CommitBox build={build} step={index} onCommit={onCommit} />
      )}
      {last?.verdict && <VerdictCard verdict={last.verdict} image={last.images[0]} />}
      {mine.length > 1 && (
        <p className="muted">{mine.length} commits for this step. See them all in the Commits tab.</p>
      )}
    </div>
  )
}

function Finished({ plan }: { plan: BuildPlan }) {
  return (
    <div className="build-section">
      <h2>What it looks like when it's finished</h2>
      <p className="muted">A reference made from the plan, not one of your commits.</p>
      {plan.model && <BenchModel model={plan.model} guide={plan.part_guide} />}
      <p className="lede">{plan.final_result}</p>
      {plan.code && (
        <details className="build-fold" open>
          <summary>Arduino code</summary>
          <pre>{plan.code}</pre>
        </details>
      )}
      {plan.safety.length > 0 && (
        <details className="build-fold">
          <summary>Safety notes</summary>
          <ul>
            {plan.safety.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function Commits({ build, plan }: { build: Build; plan: BuildPlan }) {
  const [open, setOpen] = useState<string | null>(null)
  const title = (c: BuildCommit) =>
    c.kind === 'start'
      ? 'What I had at the start'
      : c.step != null && plan.steps[c.step]
        ? `Step ${c.step + 1}: ${plan.steps[c.step].title}`
        : 'Step commit'
  return (
    <div className="build-section">
      <p className="muted">
        Every commit you made, like a history of your build: #0 is what you had at the start, then each step you
        committed, with the AI's check and a 3D model built from that commit's photos.
      </p>
      <ol className="commits">
        {build.commits.map((c, n) => (
          <li key={c.id} className="commit-card">
            <div className="commit-head">
              <span className="commit-n">#{n}</span>
              <strong>{title(c)}</strong>
              <code>{c.id}</code>
              <span className="muted">
                {new Date(c.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            {c.message && <p className="commit-message">{c.message}</p>}
            {c.images.length > 0 && (
              <div className="commit-images">
                {c.images.map((src) => (
                  <img key={src} src={src} alt="" />
                ))}
              </div>
            )}
            {c.verdict && <VerdictCard verdict={c.verdict} />}
            {!!c.detected?.length && (
              <p className="muted">
                Parts spotted: {c.detected.map((d) => `${d.quantity}× ${d.name} (${d.where})`).join(', ')}
              </p>
            )}
            {c.model && (
              <button type="button" className="tool" onClick={() => setOpen(open === c.id ? null : c.id)}>
                {open === c.id ? 'Hide 3D model' : 'Show 3D model'}
              </button>
            )}
            {c.model && open === c.id && <BenchModel model={c.model} guide={c.guide} height={360} />}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function BuildPage({ buildId }: { buildId: string }) {
  const [build, setBuild] = useState<Build | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [at, setAt] = useState(-1) // -1 overview, 0..n-1 steps, n finished
  const [tab, setTab] = useState<'guide' | 'commits'>('guide')

  useEffect(() => {
    let stop = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const b = await getBuild(buildId)
        if (stop) return
        setBuild(b)
        setError(null)
        if (b.status === 'done' && b.plan) {
          rememberProject({ design: `build/${b.id}`, title: b.plan.title, prompt: b.goal, steps: b.plan.steps.length })
        }
        if (b.status === 'done' || b.status === 'error') return
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
  }, [buildId])

  const plan = build?.status === 'done' ? build.plan : null
  const addCommit = (c: BuildCommit) => setBuild((b) => (b ? { ...b, commits: [...b.commits, c] } : b))

  if (!plan) {
    const reached = build ? STAGES.findIndex((s) => s.status === build.status) : -1
    return (
      <div className="page">
        <ProgressHeader active={2} build={buildId} />
        <main className="page-body build-wait">
          <div className="build-wait-card">
            <div className="eyebrow">Designing your build</div>
            <h1>{build?.goal || 'Loading…'}</h1>
            {build?.status === 'error' ? (
              <p className="error-text">
                {build.error || 'Planning failed.'} Wait a moment and try again from the Dashboard.
              </p>
            ) : (
              <ul className="phases">
                {STAGES.map((s, i) => (
                  <li key={s.status} className={i < reached ? 'done' : i === reached ? 'active' : ''}>
                    <span className="mark">{i < reached ? '✓' : i === reached ? '●' : '○'}</span>
                    {i === reached && build?.stage ? build.stage : s.label}
                  </li>
                ))}
              </ul>
            )}
            {error && <p className="error-text">{error}</p>}
          </div>
        </main>
      </div>
    )
  }

  const n = plan.steps.length
  const item = (i: number, label: string) => (
    <li key={i}>
      <button className={i === at ? 'active' : i < at ? 'done' : ''} onClick={() => (setAt(i), setTab('guide'))}>
        <span className="num">{i < 0 ? '0' : i >= n ? '✓' : i + 1}</span>
        {label}
      </button>
    </li>
  )
  return (
    <div className="page">
      <ProgressHeader active={3} build={buildId} />
      <div className="app">
        <aside className="sidebar">
          <header>
            <div className="eyebrow">Breadboard build</div>
            <h1>{plan.title}</h1>
            <p className="prompt">“{build!.goal}”</p>
            <ShareButton />
          </header>
          <ol className="steps">
            {item(-1, 'Your bench and parts')}
            {plan.steps.map((s, i) => item(i, s.title))}
            {item(n, 'Finished build')}
          </ol>
        </aside>
        <main className="build-main">
          <div className="build-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={tab === 'guide'}
              className={tab === 'guide' ? 'active' : ''}
              onClick={() => setTab('guide')}
            >
              Guide
            </button>
            <button
              role="tab"
              aria-selected={tab === 'commits'}
              className={tab === 'commits' ? 'active' : ''}
              onClick={() => setTab('commits')}
            >
              Commits <span className="count">{build!.commits.length}</span>
            </button>
          </div>
          {tab === 'commits' ? (
            <Commits build={build!} plan={plan} />
          ) : at < 0 ? (
            <Overview build={build!} plan={plan} />
          ) : at >= n ? (
            <Finished plan={plan} />
          ) : (
            <StepView key={at} build={build!} plan={plan} index={at} onCommit={addCommit} />
          )}
          {tab === 'guide' && (
            <div className="build-nav">
              <button type="button" className="tool" disabled={at < 0} onClick={() => setAt(at - 1)}>
                ← Back
              </button>
              <button type="button" className="primary" disabled={at >= n} onClick={() => setAt(at + 1)}>
                {at < 0 ? 'Start step 1 →' : at === n - 1 ? 'Finish →' : 'Next step →'}
              </button>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
