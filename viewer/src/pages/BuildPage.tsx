// A breadboard build (/build/<id>): Senna's Build helper flow in the main site's layout. While the
// server plans it shows the stages; then the guide: your bench now (commit #0) and the parts you
// need, one step at a time (numbered-hole picture, check line, a 3D model of the bench after the
// step, and an optional photo commit the AI checks), the finished build, and the Commits tab next to
// the build's title (hidden on ready-made guides, which nobody commits to).
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'
import {
  commitStep,
  copyBuild,
  getBuild,
  reportStep,
  setBuildSummary,
  type Build,
  type BuildCommit,
  type BuildPlan,
  type BuildStep,
  type TestPoint,
  type Verdict,
  type WireInfo,
} from '../api'
import { BenchModel, WireEnds } from '../components/BenchModel'
import { ProgressHeader } from '../components/ProgressHeader'
import { ShareButton } from '../components/ShareButton'
import { shrink } from '../images'
import { designParams, navigate, withParams } from '../router'
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

// Hardware (CAD) builds come from the design pipeline (bench/cad.py sets plan.kind = 'cad'): photos from the
// front and side instead of a breadboard from straight above.
function isHardware(plan: BuildPlan | null) {
  return plan?.kind === 'cad'
}

/** Consecutive steps with the same section, or null when the plan has no sections (breadboard builds). */
function sectionsOf(steps: BuildStep[]) {
  if (!steps.some((s) => s.section)) return null
  const groups: { name: string; start: number; end: number }[] = []
  steps.forEach((s, i) => {
    const name = s.section || 'More steps'
    const last = groups[groups.length - 1]
    if (last && last.name === name) last.end = i
    else groups.push({ name, start: i, end: i })
  })
  return groups
}

// How each step picture angle reads in its caption (iso, the default, needs no words).
const VIEW_WORDS: Record<string, string> = {
  iso_right: ', seen from the front right',
  iso_back: ', seen from the back',
  iso_left_back: ', seen from the back left',
  below: ', seen from underneath',
}

const SUMMARY_MAX = 280

/** The short project summary under the title: at most 3 lines, and the owner can rewrite it. */
function Summary({ build, plan, onSaved }: { build: Build; plan: BuildPlan; onSaved: (summary: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(plan.summary)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canEdit = !build.ready && build.mine !== false
  if (editing) {
    return (
      <form
        className="summary-edit"
        onSubmit={(e) => {
          e.preventDefault()
          setBusy(true)
          setError(null)
          setBuildSummary(build.id, text)
            .then((r) => {
              onSaved(r.summary)
              setEditing(false)
            })
            .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
            .finally(() => setBusy(false))
        }}
      >
        <textarea
          value={text}
          maxLength={SUMMARY_MAX}
          rows={4}
          autoFocus
          aria-label="Project summary"
          onChange={(e) => setText(e.target.value)}
        />
        <div className="commit-row">
          <button type="submit" className="primary" disabled={busy || text.trim().length < 3}>
            {busy ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            className="tool"
            onClick={() => {
              setEditing(false)
              setText(plan.summary)
              setError(null)
            }}
          >
            Cancel
          </button>
          <span className="muted">
            {text.length}/{SUMMARY_MAX}
          </span>
        </div>
        {error && <p className="error-text">{error}</p>}
      </form>
    )
  }
  return (
    <div className="summary">
      <p className="prompt summary-text" title={plan.summary || build.goal}>
        {plan.summary || build.goal}
      </p>
      {canEdit && (
        <button
          type="button"
          className="summary-button"
          onClick={() => {
            setText(plan.summary)
            setEditing(true)
          }}
        >
          Edit summary
        </button>
      )}
    </div>
  )
}

function VerdictCard({ verdict, image, hardware }: { verdict: Verdict; image?: string; hardware?: boolean }) {
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
        {verdict.next ? (
          verdict.status !== 'error' && <p className="verdict-next">{verdict.next}</p>
        ) : (
          <>
            {verdict.status === 'problem' && <p className="verdict-next">Fix it, then take a new photo and check again.</p>}
            {verdict.status === 'in_progress' && <p className="verdict-next">Finish the step, then check again.</p>}
          </>
        )}
        {verdict.status === 'unclear' && (
          <p className="verdict-fix">
            {hardware
              ? 'Take a sharper photo closer to the new part, with good light, from the front and from the side.'
              : 'Take a sharper photo from straight above, close enough to read the row numbers.'}
          </p>
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
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const camera = useRef<HTMLInputElement>(null)
  const hardware = isHardware(build.plan)

  const add = async (files: FileList | File[] | null) => {
    const picked = [...(files ?? [])].filter((f) => f.type.startsWith('image/')).slice(0, MAX_PHOTOS - photos.length)
    if (!picked.length) return
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
    <div
      className={`commit-box${dragging ? ' dragging' : ''}`}
      onDragOver={(e) => {
        if (busy || ![...e.dataTransfer.types].includes('Files')) return
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        if (!busy) void add(e.dataTransfer.files)
      }}
      onPaste={(e) => {
        const files = [...e.clipboardData.files].filter((f) => f.type.startsWith('image/'))
        if (files.length && !busy) {
          e.preventDefault()
          void add(files)
        }
      }}
    >
      <h3>Check this step with a photo</h3>
      <p className="muted">
        {hardware
          ? 'Take 1 to 3 photos after this step: one from the front and one from the side that shows the new part. The AI compares them with the step and tells you what is wrong and how to fix it.'
          : 'Take a photo of your bench after this step, from straight above. The AI checks it against the step and builds a 3D model of what you built.'}{' '}
        Drop photos here, paste them, or use the buttons. Each check shows up in the Commits tab.
      </p>
      <div className="commit-row">
        <button
          type="button"
          className="tool"
          onClick={() => camera.current?.click()}
          disabled={busy || photos.length >= MAX_PHOTOS}
        >
          Take photo
        </button>
        <input
          ref={camera}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          onChange={(e) => {
            void add(e.target.files)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          className="tool"
          onClick={() => picker.current?.click()}
          disabled={busy || photos.length >= MAX_PHOTOS}
        >
          Upload photos
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
          placeholder={
            hardware
              ? 'Message or question (optional), e.g. Is the pinion meshing with the rack?'
              : 'Message or question (optional), e.g. Is the red LED the right way round?'
          }
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
        <p className="muted">
          {hardware
            ? 'Comparing your photos with this step (up to a minute)…'
            : 'Checking your photos against this step and building a 3D model (up to a minute)…'}
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}

/** What the automatic checks found, so nobody builds a guide that still fails them without knowing. */
function ChecksNote({ checks }: { checks?: BuildPlan['checks'] }) {
  if (!checks) return null
  if (!checks.passed)
    return (
      <div className="checks-note checks-failed" role="alert">
        <strong>Some automatic checks still fail on this guide. Don't build it as it is.</strong>
        <ul>
          {checks.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        <span>Try describing the project again, or report the step that looks wrong.</span>
      </div>
    )
  return (
    <>
      {checks.warnings?.length ? (
        <div className="checks-note checks-warning">
          <strong>Good to know before you build:</strong>
          <ul>
            {checks.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  )
}

function Overview({ build, plan }: { build: Build; plan: BuildPlan }) {
  const start = build.commits.find((c) => c.kind === 'start')
  return (
    <div className="build-section">
      <p className="lede">{plan.summary}</p>
      <ChecksNote checks={plan.checks} />
      {isHardware(plan) ? null : <h2>Your bench now (commit #0)</h2>}
      {isHardware(plan) ? null : start?.model ? (
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
            <th>Find it</th>
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
              <td className="buy-links">
                {buyLinks(p.name).map((l, j) => (
                  <span key={l.shop}>
                    {j > 0 && ' · '}
                    <a href={l.url} target="_blank" rel="noopener noreferrer sponsored">
                      {l.shop}
                    </a>
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {plan.pin_map && plan.pin_map.length > 0 && (
        <details className="build-fold">
          <summary>Pin map (for your firmware)</summary>
          {plan.pin_map.map((b) => (
            <table className="build-table pin-map" key={b.board}>
              <caption>{b.board}</caption>
              <thead>
                <tr>
                  <th>Pin</th>
                  <th>Goes to</th>
                  <th>Wire</th>
                </tr>
              </thead>
              <tbody>
                {b.pins.map((p, i) => (
                  <tr key={i}>
                    <td>
                      <code>{p.pin}</code>
                    </td>
                    <td>{p.to.join(', ')}</td>
                    <td className="muted">{p.colour}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </details>
      )}
      {plan.steps.length > 0 && (
        <details className="build-fold">
          <summary>All steps at a glance</summary>
          <ol className="glance">
            {plan.steps.map((s, i) => (
              <li key={i}>
                <strong>{s.title}</strong> {s.instruction}
                <span className="muted"> Check: {s.check}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  )
}

// "Find it" in the parts table: a store search for each part. VITE_AMAZON_TAG (an Amazon Associates
// tracking id, set at build time) turns the Amazon links into affiliate links; without it they're plain searches.
const AMAZON_TAG = import.meta.env.VITE_AMAZON_TAG as string | undefined

function buyLinks(name: string) {
  const q = encodeURIComponent(name.replace(/\(.*?\)/g, ' ').replace(/\s+/g, ' ').trim())
  return [
    { shop: 'Amazon', url: `https://www.amazon.com/s?k=${q}${AMAZON_TAG ? `&tag=${encodeURIComponent(AMAZON_TAG)}` : ''}` },
    { shop: 'AliExpress', url: `https://www.aliexpress.com/wholesale?SearchText=${q}` },
  ]
}

function CopyBuild({ build }: { build: Build }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="commit-box">
      <h3>Build this yourself</h3>
      <p className="muted">
        This is a ready-made guide. Make your own copy to photograph each step: the AI checks your work, and your
        commits are saved with your copy.
      </p>
      <div className="commit-row">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            copyBuild(build.id).then(
              ({ id }) => navigate(withParams(`/build/${id}`, { code: designParams().code })),
              (e) => {
                setError(e instanceof Error ? e.message : String(e))
                setBusy(false)
              },
            )
          }}
        >
          {busy ? 'Copying…' : 'Make my own copy'}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}

// Step pictures are rendered at 640 × 480 (export.step_pictures); wire lines come in fractions of that.
const PIC_W = 640
const PIC_H = 480

// The step picture's on-screen width: the full step column by default (it is the step's main picture, as in
// an assembly manual), made smaller with the handle in its corner, remembered per browser.
const PIC_SIZE_KEY = 'ps.stepPictureWidth'
const PIC_MIN = 240
const PIC_MAX = 900
const PIC_DEFAULT = PIC_MAX
const clampWidth = (w: number) => Math.round(Math.min(PIC_MAX, Math.max(PIC_MIN, w)))

function loadPictureWidth(): number {
  try {
    const w = Number(localStorage.getItem(PIC_SIZE_KEY))
    return w ? clampWidth(w) : PIC_DEFAULT
  } catch {
    return PIC_DEFAULT
  }
}

function savePictureWidth(w: number) {
  try {
    localStorage.setItem(PIC_SIZE_KEY, String(w))
  } catch {
    // private mode or storage full: the size just isn't remembered
  }
}

/** Drag (mouse or touch) or arrow keys on the corner handle to resize the picture; the height follows. */
function usePictureWidth() {
  const [width, setWidth] = useState(loadPictureWidth)
  const latest = useRef(width)
  const drag = useRef<{ id: number; x: number; y: number; w: number } | null>(null)
  const resize = (w: number) => {
    latest.current = clampWidth(w)
    setWidth(latest.current)
  }
  const end = (e: ReactPointerEvent<HTMLElement>) => {
    if (drag.current?.id !== e.pointerId) return
    drag.current = null
    savePictureWidth(latest.current)
  }
  const handle = {
    onPointerDown: (e: ReactPointerEvent<HTMLElement>) => {
      e.preventDefault()
      e.currentTarget.setPointerCapture(e.pointerId)
      // Start from the width actually shown (a narrow screen may be showing less than the saved width).
      const shown = e.currentTarget.parentElement?.getBoundingClientRect().width ?? width
      drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, w: shown }
    },
    onPointerMove: (e: ReactPointerEvent<HTMLElement>) => {
      const d = drag.current
      if (!d || d.id !== e.pointerId) return
      // Follow the pointer along the picture's diagonal, so dragging right or down both make it bigger.
      const dx = e.clientX - d.x
      const dy = (e.clientY - d.y) * (PIC_W / PIC_H)
      resize(d.w + (dx + dy) / 2)
    },
    onPointerUp: end,
    onPointerCancel: end,
    onKeyDown: (e: ReactKeyboardEvent<HTMLElement>) => {
      const step = e.shiftKey ? 80 : 20
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') resize(width + step)
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') resize(width - step)
      else return
      e.preventDefault()
      savePictureWidth(latest.current)
    },
  }
  return { width, handle }
}

// The step animation (hardware steps only; breadboard pictures are stills): what you do in this step plays once
// when the step opens, always in the step picture's own frame (no zoom, no camera move). The motion
// frames rendered with the picture's camera (export.motion_frames) play, the new parts sliding in along the
// way they go (screws turning down into their holes), then the new wires draw end to end. Replay plays it
// again; the slider scrubs it. With reduced motion on, the picture opens on its last frame.
const PARTS_MS = 1800 // hardware: the parts sliding in
const WIRE_MS = 700 // hardware: each wire drawing
const SETTLE_MS = 350 // hardware: the drawn wires turning into the rendered ones
const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const easeInOut = (x: number) => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2)

/** Progress 0..1 of the step animation; plays from 0 whenever `key` changes and `ready` is true. */
function useTimeline(key: string, duration: number, ready: boolean) {
  const [t, setT] = useState(1)
  const [playing, setPlaying] = useState(false)
  const raf = useRef(0)
  const play = (from = 0) => {
    cancelAnimationFrame(raf.current)
    const start = performance.now() - from * duration
    setPlaying(true)
    setT(from)
    const tick = (now: number) => {
      const p = clamp01((now - start) / duration)
      setT(p)
      if (p < 1) raf.current = requestAnimationFrame(tick)
      else setPlaying(false)
    }
    raf.current = requestAnimationFrame(tick)
  }
  // Before paint, so a new step never flashes its last frame first.
  useLayoutEffect(() => {
    if (!ready) return
    if (reducedMotion()) {
      setT(1)
      setPlaying(false)
    } else play(0)
    return () => cancelAnimationFrame(raf.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready])
  const scrub = (p: number) => {
    cancelAnimationFrame(raf.current)
    setPlaying(false)
    setT(clamp01(p))
  }
  return { t, playing, replay: () => play(0), scrub }
}

type Frames = NonNullable<BuildStep['picture_frames']>

/** A hardware step's timeline: how long it plays, and at t (0..1) which picture shows (`pos`: 0..count in
 * frames, count being the step picture itself, fractions blending two neighbours) and how far the new wires
 * are drawn (`wire`, 0..1). */
function cadTimeline(frames: Frames | null, wireCount: number) {
  const count = frames?.count ?? 0
  const seatedAt = frames?.seated ? count - 1 : count // the frame with every part in place
  const parts = seatedAt > 0 ? PARTS_MS : 0
  const wiring = frames?.seated && wireCount ? WIRE_MS * Math.min(wireCount, 5) : 0
  const settle = frames?.seated ? SETTLE_MS : 0
  const duration = parts + wiring + settle
  const at = (t: number) => {
    const ms = t * duration
    if (ms < parts) return { pos: (ms / parts) * seatedAt, wire: 0 }
    if (ms < parts + wiring) return { pos: seatedAt, wire: (ms - parts) / wiring }
    return { pos: seatedAt + (settle ? clamp01((ms - parts - wiring) / settle) : 1) * (count - seatedAt), wire: 1 }
  }
  return { duration, at }
}

/** One frame of a hardware step's motion sprite, laid exactly over the step picture (inside its border). */
function SpriteFrame({ frames, k, opacity }: { frames: Frames; k: number; opacity: number }) {
  return (
    <div
      className="step-frame"
      aria-hidden="true"
      style={{
        backgroundImage: `url("${frames.src}")`,
        backgroundSize: `${frames.count * 100}% 100%`,
        backgroundPosition: `${frames.count > 1 ? (k / (frames.count - 1)) * 100 : 0}% 0`,
        opacity,
      }}
    />
  )
}

/** The hardware step picture with its motion on top: the frame at `pos` (blended with the next one), and
 * this step's wires drawing from end to end over the frame where the parts are seated. */
function CadMotion({
  frames,
  pos,
  wire,
  lines,
  colors,
}: {
  frames: Frames
  pos: number
  wire: number
  lines: { id: string; points: [number, number][] }[]
  colors: Record<string, string>
}) {
  if (pos >= frames.count) return null
  const a = Math.floor(pos)
  const f = pos - a
  const b = a + 1
  const fade = 1 - f // above the step picture: frame a fades out as the picture (or frame b) shows through
  const drawn = frames.seated && wire > 0
  const slot = lines.length ? 1 / lines.length : 1
  return (
    <>
      {b < frames.count ? (
        <>
          <SpriteFrame frames={frames} k={a} opacity={1} />
          {f > 0 && <SpriteFrame frames={frames} k={b} opacity={f} />}
        </>
      ) : (
        <SpriteFrame frames={frames} k={a} opacity={fade} />
      )}
      {drawn && (
        <svg className="wire-overlay wire-draw" viewBox={`0 0 ${PIC_W} ${PIC_H}`} preserveAspectRatio="none" aria-hidden="true" style={{ opacity: fade }}>
          {lines.map((l, k) => {
            const u = clamp01((wire - k * slot) / (slot * 1.25))
            if (u <= 0) return null
            const pts = l.points.map((p) => `${p[0] * PIC_W},${p[1] * PIC_H}`).join(' ')
            const style = { strokeDasharray: '1 1', strokeDashoffset: 1 - easeInOut(u) }
            return (
              <g key={l.id}>
                <polyline points={pts} pathLength={1} className="wire-draw-shadow" style={style} />
                <polyline points={pts} pathLength={1} className="wire-draw-core" style={{ ...style, stroke: colors[l.id] }} />
              </g>
            )
          })}
        </svg>
      )}
    </>
  )
}

/** Whether a hardware step's motion sprite has loaded (null while loading), so it never plays half-loaded. */
function useSpriteLoaded(src: string | undefined) {
  const [done, setDone] = useState<{ src: string; ok: boolean } | null>(null)
  useEffect(() => {
    if (!src) return
    let live = true
    const img = new Image()
    img.onload = () => live && setDone({ src, ok: true })
    img.onerror = () => live && setDone({ src, ok: false })
    img.src = src
    return () => {
      live = false
    }
  }, [src])
  return !src ? false : done?.src === src ? done.ok : null
}

function AnimControls({ t, playing, onReplay, onScrub }: { t: number; playing: boolean; onReplay: () => void; onScrub: (p: number) => void }) {
  return (
    <div className="step-anim">
      <button type="button" className="step-anim-replay" onClick={onReplay} disabled={playing} title="Play this step's animation again">
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M3 8a5 5 0 1 0 1.5-3.6M3 2.5v2.8h2.8" />
        </svg>
        {playing ? 'Playing…' : 'Replay'}
      </button>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={Math.round(t * 100)}
        onChange={(e) => onScrub(Number(e.target.value) / 100)}
        aria-label="Scrub through this step's animation"
        aria-valuetext={`${Math.round(t * 100)} %`}
      />
      <span className="step-anim-pct">{Math.round(t * 100)} %</span>
    </div>
  )
}

/** A step's picture. On hardware builds every wire in it is clickable: the wire lights up and both ends
 * are tagged with the part and pin they plug into. */
function StepPicture({
  step,
  index,
  wires,
  caption,
}: {
  step: BuildStep
  index: number
  wires: Record<string, WireInfo>
  caption: string
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const { width, handle } = usePictureWidth()
  const src = step.picture ?? ''
  const alt = `Step ${index + 1}: where each part goes`
  const isSvg = /\.svg(\?|#|$)/i.test(src) // breadboard pictures: shown still, no animation
  const lines = (step.picture_wires ?? []).filter((l) => wires[l.id] && l.points.length > 1)
  // Hardware: the motion frames (none on pictures made before them: those show still) and this step's wires.
  const sprite = useSpriteLoaded(isSvg ? undefined : step.picture_frames?.src)
  const frames = sprite ? step.picture_frames! : null
  const fresh = new Set(step.model?.new ?? step.part_ids)
  const newLines = lines.filter((l) => fresh.has(l.id))
  const cad = cadTimeline(frames, newLines.length)
  const animated = cad.duration > 0
  const { t, playing, replay, scrub } = useTimeline(src, cad.duration || 1, sprite !== null)
  const motion = frames && t < 1 ? cad.at(t) : null
  const line = lines.find((l) => l.id === picked)
  const wire = picked ? wires[picked] : undefined
  const at = (p: [number, number]) => [p[0] * PIC_W, p[1] * PIC_H] as const
  const pts = (l: { points: [number, number][] }) => l.points.map((p) => at(p).join(',')).join(' ')
  return (
    <figure className="step-figure" style={{ maxWidth: width }}>
      <div className="step-picture-wrap">
        <img className="step-picture" src={src} alt={alt} />
        {frames && motion && (
          <CadMotion
            frames={frames}
            pos={motion.pos}
            wire={motion.wire}
            lines={newLines}
            colors={Object.fromEntries(newLines.map((l) => [l.id, wires[l.id].color]))}
          />
        )}
        {lines.length > 0 && (
          <svg className="wire-overlay" viewBox={`0 0 ${PIC_W} ${PIC_H}`} preserveAspectRatio="none">
            {lines.map((l) => (
              <polyline
                key={l.id}
                points={pts(l)}
                className="wire-hit"
                onClick={() => setPicked(l.id === picked ? null : l.id)}
              >
                <title>{`${wires[l.id].from.part} ${wires[l.id].from.pin} → ${wires[l.id].to.part} ${wires[l.id].to.pin}`}</title>
              </polyline>
            ))}
            {line && wire && (
              <g className="wire-picked" pointerEvents="none">
                <polyline points={pts(line)} className="wire-glow" />
                <polyline points={pts(line)} style={{ stroke: wire.color }} className="wire-core" />
                {[line.points[0], line.points[line.points.length - 1]].map((p, i) => {
                  const [x, y] = at(p)
                  const end = i === 0 ? wire.from : wire.to
                  const right = x < PIC_W * 0.62
                  return (
                    <g key={i} transform={`translate(${x},${y})`}>
                      <circle r={9} className="wire-dot" />
                      <text className="wire-dot-tag" textAnchor="middle" dy="4">
                        {i === 0 ? 'A' : 'B'}
                      </text>
                      <text className="wire-pin-label" x={right ? 14 : -14} dy="5" textAnchor={right ? 'start' : 'end'}>
                        {`${end.part} · ${end.pin}`}
                      </text>
                    </g>
                  )
                })}
              </g>
            )}
          </svg>
        )}
        <div
          className="picture-resize"
          role="slider"
          tabIndex={0}
          aria-label="Picture size: drag or use the arrow keys"
          aria-valuemin={PIC_MIN}
          aria-valuemax={PIC_MAX}
          aria-valuenow={width}
          title="Drag to resize the picture"
          {...handle}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M15 6 6 15M15 11l-4 4" />
          </svg>
        </div>
      </div>
      {animated && <AnimControls t={t} playing={playing} onReplay={replay} onScrub={scrub} />}
      {wire && (
        <p className="wire-info">
          <WireEnds wire={wire} />
        </p>
      )}
      <figcaption className="muted">
        {caption}
        {lines.length > 0 && !wire ? ' Click a wire to see the pin at each end.' : ''}
      </figcaption>
    </figure>
  )
}

/** "Parts in 4/9 · Wires in 2/9": how much of the build is in after this step. */
function Progress({ plan, index }: { plan: BuildPlan; index: number }) {
  const kinds = new Map((plan.model?.labels ?? []).map((l) => [l.id, l.kind]))
  const count = (upto: number, wire: boolean) => {
    const ids = new Set(plan.steps.slice(0, upto).flatMap((s) => s.model?.new ?? s.part_ids))
    return [...ids].filter((id) => kinds.has(id) && (kinds.get(id) === 'wire') === wire && !/^(breadboard|development_board)$/.test(kinds.get(id) ?? '')).length
  }
  const total = plan.steps.length
  const parts = [count(index + 1, false), count(total, false)]
  const wires = [count(index + 1, true), count(total, true)]
  return (
    <div className="step-progress" aria-label="Build progress">
      {parts[1] > 0 && (
        <span>
          <i>Parts in</i> <b>{parts[0]}</b>/{parts[1]}
        </span>
      )}
      {wires[1] > 0 && (
        <span>
          <i>Wires in</i> <b>{wires[0]}</b>/{wires[1]}
        </span>
      )}
    </div>
  )
}

function StepView({
  build,
  plan,
  index,
  onCommit,
  onNext,
}: {
  build: Build
  plan: BuildPlan
  index: number
  onCommit: (c: BuildCommit) => void
  onNext: () => void
}) {
  const s = plan.steps[index]
  const mine = build.commits.filter((c) => c.kind === 'step' && c.step === index)
  const last = mine[mine.length - 1]
  const fresh = s.model?.new ?? s.part_ids
  const freshNames = (s.model?.labels ?? []).filter((l) => fresh.includes(l.id) && l.kind !== 'wire')
  return (
    <div className="build-section">
      <div className="step-head">
        <div className="step-badge" aria-label={`Step ${index + 1} of ${plan.steps.length}`}>
          <span className="step-big">{index + 1}</span>
          <span className="step-of">of {plan.steps.length}</span>
        </div>
        <Progress plan={plan} index={index} />
      </div>
      <h2 className="step-title">{s.title}</h2>
      {isHardware(plan) && s.model && (
        // hardware: the live 3D build is the main picture (framed on this step's parts, which drop into place)
        <BenchModel model={s.model} guide={plan.part_guide} wires={plan.wires} highlight={fresh} height={460} />
      )}
      {isHardware(plan) && freshNames.length > 0 && (
        <ul className="new-parts">
          {freshNames.map((l) => (
            <li key={l.id}>
              <span className="pill">new</span> <strong>{l.name}</strong>
              {' · '}
              {plan.part_guide[l.id] || 'placed in this step'}
            </li>
          ))}
        </ul>
      )}
      {!isHardware(plan) && s.picture && (
        <StepPicture
          key={index}
          step={s}
          index={index}
          wires={plan.wires ?? {}}
          caption={
            isHardware(plan)
              ? `${s.picture_close_up ? 'A close-up of the build after this step' : 'The build after this step'}${VIEW_WORDS[s.picture_view ?? 'iso'] ?? ''}. Cyan is what you add now; the AI compares your photos with this picture.`
              : 'Cyan is what you place in this step; faded parts are from earlier steps. Numbers match the list below.'
          }
        />
      )}
      {s.why && <p className="step-why">{s.why}</p>}
      <p className="step-text">{s.instruction}</p>
      {!!s.tools?.length && (
        <p className="step-tools">
          <span>You need</span> {s.tools.join(', ')}
        </p>
      )}
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
      {isHardware(plan) && s.picture && (
        <details className="step-reference">
          <summary>The picture the camera check compares your photo with</summary>
          <StepPicture key={index} step={s} index={index} wires={plan.wires ?? {}} caption="The AI compares your photos with this render. Cyan is what you add now." />
        </details>
      )}
      {s.model && !isHardware(plan) && (
        <>
          <h3>Your bench after step {index + 1}</h3>
          <p className="muted">Your starting bench plus everything added so far, with this step's parts highlighted.</p>
          <BenchModel model={s.model} guide={plan.part_guide} wires={plan.wires} highlight={fresh} />
          {freshNames.length > 0 && (
            <ul className="new-parts">
              {freshNames.map((l) => (
                <li key={l.id}>
                  <span className="pill">new</span> <strong>{l.name}</strong>
                  {' · '}
                  {plan.part_guide[l.id] || 'placed in this step'}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {build.ready ? (
        <CopyBuild build={build} />
      ) : build.mine === false ? (
        <p className="muted shared-note">
          {build.owner_name ? `${build.owner_name} shared this build with you.` : 'This build was shared with you.'}{' '}
          Only the person who started it can commit photos to it.
        </p>
      ) : (
        <CommitBox key={index} build={build} step={index} onCommit={onCommit} />
      )}
      {last?.verdict && <VerdictCard verdict={last.verdict} image={last.images[0]} hardware={isHardware(plan)} />}
      {last?.verdict?.status === 'done' && (
        <div className="commit-row">
          <button type="button" className="primary" onClick={onNext}>
            {index === plan.steps.length - 1 ? 'Finish →' : `On to step ${index + 2} →`}
          </button>
        </div>
      )}
      {mine.length > 1 && (
        <p className="muted">{mine.length} commits for this step. See them all in the Commits tab.</p>
      )}
      {plan.tests
        ?.filter((t) => t.after_step === index + 1)
        .map((t) => <TestCard key={t.title} test={t} />)}
      <ReportStep key={index} buildId={build.id} step={index} />
    </div>
  )
}

/** A sketch with Copy and Download buttons (download as name.ino, the Arduino IDE's file type). */
function CodeBlock({ code, name }: { code: string; name: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="code-block">
      <div className="code-actions">
        <button
          type="button"
          className="tool"
          onClick={() =>
            navigator.clipboard.writeText(code).then(
              () => {
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              },
              () => {},
            )
          }
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
        <a
          className="tool"
          download={`${name}.ino`}
          href={`data:text/plain;charset=utf-8,${encodeURIComponent(code)}`}
        >
          Download .ino
        </a>
      </div>
      <pre>{code}</pre>
    </div>
  )
}

const sketchName = (title: string) =>
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40) || 'sketch'

/** "Test it now": an optional check after this step, so a beginner finds a mistake before building on it. */
function TestCard({ test }: { test: TestPoint }) {
  return (
    <details className="test-card">
      <summary>
        <span className="test-badge">optional test</span> {test.title}
      </summary>
      <p>{test.what_it_tests}</p>
      <CodeBlock code={test.code} name={sketchName(test.title)} />
      <p>
        <strong>What you should see:</strong> {test.expect}
      </p>
      <p className="muted">
        <strong>If it doesn't work:</strong> {test.if_not}
      </p>
    </details>
  )
}

/** The Code tab: the full sketch from the start of the build, and every test checkpoint in build order. */
function CodeView({ plan, onStep }: { plan: BuildPlan; onStep: (index: number) => void }) {
  const tests = plan.tests ?? []
  return (
    <div className="build-section">
      <h2>Code</h2>
      {plan.code ? (
        <>
          <p className="muted">
            The finished sketch. Upload it from the Arduino IDE once every step is done. The pin numbers match the
            steps.
          </p>
          <CodeBlock code={plan.code} name={sketchName(plan.title)} />
        </>
      ) : (
        <p className="muted">This build doesn't need a sketch.</p>
      )}
      {tests.length > 0 && (
        <>
          <h2>Test as you go</h2>
          <p className="muted">
            Optional: each short sketch below uses only what's wired by its step, so you can check that part works
            before you carry on.
          </p>
          <ol className="test-list">
            {tests.map((t) => (
              <li key={t.after_step}>
                <h3>
                  After step {t.after_step}: {t.title}{' '}
                  <button type="button" className="link" onClick={() => onStep(t.after_step - 1)}>
                    go to step {t.after_step}
                  </button>
                </h3>
                <p>{t.what_it_tests}</p>
                <CodeBlock code={t.code} name={sketchName(t.title)} />
                <p>
                  <strong>What you should see:</strong> {t.expect}
                </p>
                <p className="muted">
                  <strong>If it doesn't work:</strong> {t.if_not}
                </p>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

/** A wrong step can cost someone a board, so anyone reading a guide can flag one for a person to fix. */
function ReportStep({ buildId, step }: { buildId: string; step: number }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [error, setError] = useState<string | null>(null)
  if (state === 'sent') return <p className="muted report-step">Thanks. We'll look at this step.</p>
  if (!open)
    return (
      <button type="button" className="link report-step" onClick={() => setOpen(true)}>
        Something wrong with this step?
      </button>
    )
  return (
    <form
      className="report-step"
      onSubmit={(e) => {
        e.preventDefault()
        setState('sending')
        setError(null)
        reportStep(buildId, step, text).then(
          () => setState('sent'),
          (err) => {
            setError(err instanceof Error ? err.message : String(err))
            setState('idle')
          },
        )
      }}
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={1000}
        rows={2}
        autoFocus
        placeholder="What's wrong? e.g. the resistor goes in row 12, not 14"
        aria-label="What's wrong with this step"
      />
      <div className="commit-row">
        <button type="submit" disabled={state === 'sending' || text.trim().length < 3}>
          {state === 'sending' ? 'Sending…' : 'Send report'}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </form>
  )
}

function Finished({ plan }: { plan: BuildPlan }) {
  return (
    <div className="build-section">
      <h2>What it looks like when it's finished</h2>
      <p className="muted">A reference made from the plan, not one of your commits.</p>
      {plan.model && <BenchModel model={plan.model} guide={plan.part_guide} wires={plan.wires} />}
      <p className="lede">{plan.final_result}</p>
      {plan.imported && (
        <details className="build-fold" open={!!plan.imported.model}>
          <summary>
            CAD from the project you imported{' '}
            <a href={plan.imported.url} target="_blank" rel="noreferrer">
              ({plan.imported.title})
            </a>
          </summary>
          {plan.imported.model && <BenchModel model={plan.imported.model} height={320} />}
          {plan.imported.files.length > 0 && (
            <ul>
              {plan.imported.files.map((f) => (
                <li key={f.url}>
                  <a href={f.url} target="_blank" rel="noreferrer">
                    {f.name}
                  </a>
                  {f.note ? <span className="muted"> · {f.note}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </details>
      )}
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
      <div className="commit-row">
        <a
          className="tool"
          href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(plan, null, 2))}`}
          download="build_plan.json"
        >
          Download the build plan (JSON)
        </a>
        {plan.model && (
          <a className="tool" href={plan.model.glb} download>
            Download the finished 3D model (GLB)
          </a>
        )}
      </div>
    </div>
  )
}

export function Commits({ build, plan }: { build: Build; plan: BuildPlan }) {
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
            {c.verdict && <VerdictCard verdict={c.verdict} hardware={isHardware(plan)} />}
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
  const [tab, setTab] = useState<'guide' | 'code' | 'commits'>('guide')
  useEffect(() => {
    window.scrollTo({ top: 0 }) // braces: newer Chromium returns a Promise here, which React would take for a cleanup
  }, [tab]) // a new tab starts at its top, not where the last one was
  const [open, setOpen] = useState<Record<number, boolean>>({}) // sections the builder opened or closed
  const steps = build?.plan?.steps.length ?? 0
  useEffect(() => {
    // A new step starts at its top (Next is in the bar at the bottom), and the sidebar keeps it in view.
    document.querySelector('.build-main')?.scrollTo({ top: 0 })
    document.querySelector('.sidebar .steps button.active')?.scrollIntoView({ block: 'nearest' })
  }, [at])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (tab !== 'guide' || e.metaKey || e.ctrlKey || e.altKey || (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)))) return
      if (e.key === ']') setAt((a) => Math.min(steps, a + 1))
      else if (e.key === '[') setAt((a) => Math.max(-1, a - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab, steps])

  useEffect(() => {
    let stop = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const b = await getBuild(buildId)
        if (stop) return
        setBuild(b)
        setError(null)
        if (b.status === 'done' && b.plan && !b.ready) {
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
  const title = plan?.title
  useEffect(() => {
    if (title) document.title = `${title} · Physical Studio`
  }, [title])
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
  const groups = sectionsOf(plan.steps)
  const item = (i: number, label: string) => (
    <li key={i}>
      <button className={i === at ? 'active' : i < at ? 'done' : ''} onClick={() => (setAt(i), setTab('guide'))}>
        <span className="num">{i < 0 ? '0' : i >= n ? '✓' : i + 1}</span>
        {label}
        {plan.tests?.some((t) => t.after_step === i + 1) && (
          <span className="test-badge" title="An optional test you can run after this step">
            test
          </span>
        )}
      </button>
    </li>
  )
  return (
    <div className="page">
      <ProgressHeader active={3} build={buildId} />
      <div className="app">
        <aside className="sidebar">
          <header>
            <div className="eyebrow">{isHardware(plan) ? 'Hardware build' : 'Breadboard build'}</div>
            <div className="build-title">
              <h1>{plan.title}</h1>
              {(plan.code || !!plan.tests?.length) && (
                <button
                  type="button"
                  className={tab === 'code' ? 'active' : ''}
                  aria-pressed={tab === 'code'}
                  title={tab === 'code' ? 'Back to the guide' : 'The Arduino sketch and the tests you can run while you build'}
                  onClick={() => setTab(tab === 'code' ? 'guide' : 'code')}
                >
                  Code
                </button>
              )}
              {!build!.ready && (
                <button
                  type="button"
                  className={tab === 'commits' ? 'active' : ''}
                  aria-pressed={tab === 'commits'}
                  title={tab === 'commits' ? 'Back to the guide' : `This build's commits`}
                  onClick={() => setTab(tab === 'commits' ? 'guide' : 'commits')}
                >
                  Commits <span className="count">{build!.commits.length}</span>
                </button>
              )}
            </div>
            <Summary
              build={build!}
              plan={plan}
              onSaved={(summary) => setBuild((b) => (b?.plan ? { ...b, plan: { ...b.plan, summary } } : b))}
            />
            <ShareButton />
            <div className="build-progress" role="progressbar" aria-valuemin={0} aria-valuemax={n} aria-valuenow={Math.max(0, Math.min(at, n))}>
              <i style={{ width: `${(Math.max(0, Math.min(at, n)) / n) * 100}%` }} />
            </div>
            <div className="build-progress-label">
              {at >= n ? 'All steps done' : at < 0 ? `${n} steps` : `Step ${at + 1} of ${n}`}
            </div>
          </header>
          <ol className="steps">
            {item(-1, isHardware(plan) ? 'Parts list' : 'Your bench and parts')}
            {groups
              ? groups.map((g, gi) => {
                  const here = at >= g.start && at <= g.end
                  const expanded = open[gi] ?? here
                  return (
                    <li key={`section-${gi}`} className="step-section">
                      <button
                        type="button"
                        className={`section-head${here ? ' current' : ''}`}
                        aria-expanded={expanded}
                        onClick={() => setOpen((o) => ({ ...o, [gi]: !expanded }))}
                      >
                        <span className="chev" aria-hidden="true">
                          {expanded ? '▾' : '▸'}
                        </span>
                        <span className="section-name">{g.name}</span>
                        <span className="section-count">{at > g.end ? '✓' : `${g.start + 1}–${g.end + 1}`}</span>
                      </button>
                      {expanded && (
                        <ol className="steps nested">
                          {plan.steps.slice(g.start, g.end + 1).map((s, k) => item(g.start + k, s.title))}
                        </ol>
                      )}
                    </li>
                  )
                })
              : plan.steps.map((s, i) => item(i, s.title))}
            {item(n, 'Finished build')}
          </ol>
        </aside>
        <main className="build-main">
          {tab === 'commits' ? (
            <>
              <div className="build-nav">
                <button type="button" className="tool" onClick={() => setTab('guide')}>
                  ← Back to the guide
                </button>
              </div>
              <Commits build={build!} plan={plan} />
            </>
          ) : tab === 'code' ? (
            <>
              <div className="build-nav">
                <button type="button" className="tool" onClick={() => setTab('guide')}>
                  ← Back to the guide
                </button>
              </div>
              <CodeView plan={plan} onStep={(i) => (setAt(i), setTab('guide'))} />
            </>
          ) : at < 0 ? (
            <Overview build={build!} plan={plan} />
          ) : at >= n ? (
            <Finished plan={plan} />
          ) : (
            // Not keyed by step: the 3D model stays mounted from step to step and swaps in the next step's model
            // instead of going blank; the per-step parts (commit box, pictures, report) are keyed by step inside.
            <StepView
              build={build!}
              plan={plan}
              index={at}
              onCommit={addCommit}
              onNext={() => setAt(at + 1)}
            />
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
