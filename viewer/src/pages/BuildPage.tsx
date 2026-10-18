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
  setBuildSummary,
  type Build,
  type BuildCommit,
  type BuildPlan,
  type BuildStep,
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

function Overview({ build, plan }: { build: Build; plan: BuildPlan }) {
  const start = build.commits.find((c) => c.kind === 'start')
  return (
    <div className="build-section">
      <p className="lede">{plan.summary}</p>
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

// The step picture's on-screen width: small by default, resized with the handle in its corner, remembered
// per browser.
const PIC_SIZE_KEY = 'ps.stepPictureWidth'
const PIC_DEFAULT = 460
const PIC_MIN = 240
const PIC_MAX = 900
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

// The step animation: what you do in this step plays once when the step opens, always in the step
// picture's own frame (no zoom, no camera move). Breadboard steps: this step's parts slide down into their
// holes, then its wires draw from end to end, over the faded earlier steps. Hardware steps: the motion
// frames rendered with the picture's camera (export.motion_frames) play, the new parts sliding in along the
// way they go (screws turning down into their holes), then the new wires draw end to end. Replay plays it
// again; the slider scrubs it. With reduced motion on, the picture opens on its last frame.
const DROP = 110 // how far above its holes a breadboard part starts, in SVG units (the picture is 330 tall)
const PARTS_MS = 1800 // hardware: the parts sliding in
const WIRE_MS = 700 // hardware: each wire drawing
const SETTLE_MS = 350 // hardware: the drawn wires turning into the rendered ones
const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const easeOut = (x: number) => 1 - (1 - x) ** 3
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

type AnimItem = { el: SVGGElement; kind: 'part' | 'wire'; paths: { el: SVGGeometryElement; len: number }[] }
type Anim = { items: AnimItem[]; marks: SVGGElement | null }

const HALO = '#26c6da'
let svgCount = 0

/** Drop anything that could run code, and give the SVG's ids (the hole pattern) a prefix of their own. */
function cleanSvg(svg: SVGSVGElement) {
  svg.querySelectorAll('script, foreignObject').forEach((el) => el.remove())
  const prefix = `ps${++svgCount}-`
  const ids = Array.from(svg.querySelectorAll('[id]'), (el) => el.id)
  const all = [svg, ...Array.from(svg.querySelectorAll('*'))]
  for (const el of all) {
    for (const a of Array.from(el.attributes)) {
      if (/^on/i.test(a.name) || (/href$/i.test(a.name) && /^\s*javascript:/i.test(a.value))) {
        el.removeAttribute(a.name)
        continue
      }
      let v = a.value
      for (const id of ids) {
        v = v.split(`url(#${id})`).join(`url(#${prefix}${id})`)
        if (v === `#${id}`) v = `#${prefix}${id}`
      }
      if (a.name === 'id') v = prefix + v
      if (v !== a.value) el.setAttribute(a.name, v)
    }
  }
}

/** Pictures drawn before diagram.py tagged its new parts: find them after the faded group and tag them the
 * same way (numbered markers last, wires are the curved paths, each part starts at its legs or halo). */
function tagLegacySvg(svg: SVGSVGElement) {
  if (svg.querySelector('.ps-new, .ps-marks')) return
  const kids = Array.from(svg.children)
  const faded = kids.findIndex((el) => el.tagName === 'g' && el.getAttribute('opacity') === '.35')
  if (faded < 0) return
  const after = kids.slice(faded + 1)
  const wrap = (els: Element[], cls: string, kind?: string) => {
    if (!els.length) return
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    g.setAttribute('class', cls)
    if (kind) g.setAttribute('data-anim', kind)
    els[0].before(g)
    els.forEach((el) => g.appendChild(el))
  }
  const isMarker = (els: Element[]) =>
    els.length === 4 &&
    els[0].tagName === 'circle' && els[0].getAttribute('r') === '5' &&
    els[1].tagName === 'line' &&
    els[2].tagName === 'circle' && els[2].getAttribute('r') === '8' &&
    els[3].tagName === 'text'
  let m = after.length
  while (m >= 4 && isMarker(after.slice(m - 4, m))) m -= 4
  wrap(after.slice(m), 'ps-marks')
  const groups: { kind: string; els: Element[] }[] = []
  for (const el of after.slice(0, m)) {
    const last = groups[groups.length - 1]
    const d = el.getAttribute('d') ?? ''
    if (el.tagName === 'path' && d.includes('C')) {
      if (last?.kind === 'wire' && last.els[0].getAttribute('d') === d) last.els.push(el)
      else groups.push({ kind: 'wire', els: [el] })
      continue
    }
    const legs = el.tagName === 'path' && el.getAttribute('stroke') === '#8a8a8a'
    const halo = el.getAttribute('stroke') === HALO
    const afterLegs = last?.kind === 'part' && last.els[last.els.length - 1].getAttribute('stroke') === '#8a8a8a'
    if (!last || last.kind !== 'part' || legs || (halo && !afterLegs)) groups.push({ kind: 'part', els: [el] })
    else last.els.push(el)
  }
  groups.forEach((g) => wrap(g.els, 'ps-new', g.kind))
}

function collectAnim(svg: SVGSVGElement): Anim {
  const items = Array.from(svg.querySelectorAll<SVGGElement>('g.ps-new')).map((el) => {
    const kind = el.getAttribute('data-anim') === 'wire' ? 'wire' : 'part'
    const paths =
      kind === 'wire'
        ? Array.from(el.querySelectorAll<SVGGeometryElement>('path, line, polyline')).map((p) => ({ el: p, len: p.getTotalLength() }))
        : []
    return { el, kind, paths } as AnimItem
  })
  // Parts go in first, then the wires between them.
  items.sort((a, b) => (a.kind === b.kind ? 0 : a.kind === 'part' ? -1 : 1))
  return { items, marks: svg.querySelector<SVGGElement>('g.ps-marks') }
}

/** Show frame t (0..1): each new item gets its own slice of the first 85 %, the numbered markers the rest. */
function applyAnim({ items, marks }: Anim, t: number) {
  const span = items.length ? 0.85 : 0
  const slot = items.length ? span / items.length : 0
  items.forEach((it, k) => {
    const a = k * slot
    const u = clamp01((t - a) / (slot * 1.25))
    if (it.kind === 'part') {
      it.el.style.transform = u >= 1 ? '' : `translate(0px, ${(-DROP * (1 - easeOut(u))).toFixed(2)}px)`
      it.el.style.opacity = u >= 1 ? '' : String(clamp01(u * 3))
    } else {
      it.el.style.opacity = u > 0 ? '' : '0'
      for (const p of it.paths) {
        p.el.style.strokeDasharray = u >= 1 ? '' : `${p.len} ${p.len}`
        p.el.style.strokeDashoffset = u >= 1 ? '' : String(p.len * (1 - easeInOut(u)))
      }
    }
  })
  if (marks) marks.style.opacity = t >= 1 ? '' : String(clamp01((t - span) / (1 - span)))
}

/** A breadboard step's SVG drawn inline, so its new parts and wires can move. Calls onReady with the number
 * of things it animates, or with -1 if the SVG can't be loaded (the page then shows it as a plain image). */
function AnimatedSvg({ src, alt, t, onReady }: { src: string; alt: string; t: number; onReady: (n: number) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const anim = useRef<Anim | null>(null)
  useEffect(() => {
    let live = true
    anim.current = null
    fetch(src)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((text) => {
        if (!live || !box.current) return
        const svg = new DOMParser().parseFromString(text, 'image/svg+xml').documentElement
        if (!(svg instanceof SVGSVGElement)) throw new Error('not an svg')
        cleanSvg(svg)
        tagLegacySvg(svg)
        svg.setAttribute('class', 'step-picture')
        svg.setAttribute('role', 'img')
        svg.setAttribute('aria-label', alt)
        const node = document.importNode(svg, true)
        box.current.replaceChildren(node)
        anim.current = collectAnim(node)
        applyAnim(anim.current, 0)
        onReady(anim.current.items.length)
      })
      .catch(() => live && onReady(-1))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])
  useEffect(() => {
    if (anim.current) applyAnim(anim.current, t)
  }, [t])
  return <div ref={box} className="step-svg" />
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
  const isSvg = /\.svg(\?|#|$)/i.test(src)
  // Breadboard SVGs: how many parts/wires it animates once loaded (-1: couldn't inline it, no animation).
  const [svgItems, setSvgItems] = useState<{ src: string; n: number } | null>(null)
  const loaded = svgItems?.src === src ? svgItems.n : null
  const lines = (step.picture_wires ?? []).filter((l) => wires[l.id] && l.points.length > 1)
  // Hardware: the motion frames (none on pictures made before them: those show still) and this step's wires.
  const sprite = useSpriteLoaded(isSvg ? undefined : step.picture_frames?.src)
  const frames = sprite ? step.picture_frames! : null
  const fresh = new Set(step.model?.new ?? step.part_ids)
  const newLines = lines.filter((l) => fresh.has(l.id))
  const cad = cadTimeline(frames, newLines.length)
  const animated = isSvg ? loaded !== null && loaded >= 0 : cad.duration > 0
  const duration = isSvg ? Math.min(6000, 700 * Math.max(1, loaded ?? 1) + 500) : cad.duration || 1
  const { t, playing, replay, scrub } = useTimeline(src, duration, isSvg ? loaded !== null : sprite !== null)
  const motion = frames && t < 1 ? cad.at(t) : null
  const line = lines.find((l) => l.id === picked)
  const wire = picked ? wires[picked] : undefined
  const at = (p: [number, number]) => [p[0] * PIC_W, p[1] * PIC_H] as const
  const pts = (l: { points: [number, number][] }) => l.points.map((p) => at(p).join(',')).join(' ')
  return (
    <figure className="step-figure" style={{ maxWidth: width }}>
      <div className="step-picture-wrap">
        {isSvg && loaded !== -1 ? (
          <AnimatedSvg src={src} alt={alt} t={t} onReady={(n) => setSvgItems({ src, n })} />
        ) : (
          <>
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
          </>
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
      <div className="step-badge" aria-label={`Step ${index + 1} of ${plan.steps.length}`}>
        <span className="step-big">{index + 1}</span>
        <span className="step-of">of {plan.steps.length}</span>
      </div>
      <h2 className="step-title">{s.title}</h2>
      {s.picture && (
        <StepPicture
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
      {s.model && (
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
        <CommitBox build={build} step={index} onCommit={onCommit} />
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
    </div>
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
  const [tab, setTab] = useState<'guide' | 'commits'>('guide')
  const [open, setOpen] = useState<Record<number, boolean>>({}) // sections the builder opened or closed

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
          ) : at < 0 ? (
            <Overview build={build!} plan={plan} />
          ) : at >= n ? (
            <Finished plan={plan} />
          ) : (
            <StepView
              key={at}
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
