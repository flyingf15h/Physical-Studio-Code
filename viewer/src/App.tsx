import { Suspense, useCallback, useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Bounds, OrbitControls } from '@react-three/drei'
import { Assembly } from './Assembly'
import { loadSteps, type StepsDoc } from './steps'
import { TrackerPanel } from './tracker/TrackerPanel'
import type { Problem } from './tracker/session'
import './App.css'

const PLAY_INTERVAL_MS = 3500

interface Source {
  doc: StepsDoc
  glbUrl: string
  label: string
}

// ?design=out/<title> loads the MCP server's latest export (served by vite.config.ts);
// the default is the bundled sample.
async function loadFromUrl(): Promise<Source> {
  const base = (new URLSearchParams(location.search).get('design') ?? 'sample').replace(/\/$/, '')
  const doc = await loadSteps(`${base}/design.steps.json?t=${Date.now()}`)
  return { doc, glbUrl: `${base}/${doc.model}?t=${Date.now()}`, label: base }
}

async function loadFromFiles(files: FileList): Promise<Source> {
  const list = Array.from(files)
  const json = list.find((f) => f.name.endsWith('.json'))
  const glb = list.find((f) => f.name.endsWith('.glb'))
  if (!json || !glb) throw new Error('Drop the .glb and the .steps.json together.')
  const doc = JSON.parse(await json.text()) as StepsDoc
  if (doc.format !== 'physical-studio-steps') throw new Error(`${json.name} is not a Physical Studio steps file`)
  doc.steps.sort((a, b) => a.index - b.index)
  return { doc, glbUrl: URL.createObjectURL(glb), label: glb.name }
}

export default function App() {
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [exploded, setExploded] = useState(false)
  const [problem, setProblem] = useState<Problem | null>(null)

  const use = useCallback((s: Source) => {
    setSource(s)
    setStep(0)
    setError(null)
  }, [])

  useEffect(() => {
    loadFromUrl().then(use, (e) => setError(String(e.message ?? e)))
  }, [use])

  const count = source?.doc.steps.length ?? 0
  const go = useCallback((i: number) => setStep(Math.max(0, Math.min(count - 1, i))), [count])

  useEffect(() => {
    if (!playing) return
    if (step >= count - 1) {
      setPlaying(false)
      return
    }
    const t = setTimeout(() => go(step + 1), PLAY_INTERVAL_MS)
    return () => clearTimeout(t)
  }, [playing, step, count, go])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'ArrowRight') go(step + 1)
      else if (e.key === 'ArrowLeft') go(step - 1)
      else if (e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (e.key === 'e') setExploded((x) => !x)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, step])

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    loadFromFiles(e.dataTransfer.files).then(use, (err) => setError(String(err.message ?? err)))
  }

  const current = source?.doc.steps[step]

  return (
    <div className="app" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
      <aside className="sidebar">
        <header>
          <div className="eyebrow">Physical Studio</div>
          <h1>{source?.doc.title ?? 'Loading…'}</h1>
          {source?.doc.prompt && <p className="prompt">“{source.doc.prompt}”</p>}
        </header>
        <ol className="steps">
          {source?.doc.steps.map((s, i) => (
            <li key={s.index}>
              <button className={i === step ? 'active' : i < step ? 'done' : ''} onClick={() => go(i)}>
                <span className="num">{i + 1}</span>
                {s.title}
              </button>
            </li>
          ))}
        </ol>
        <footer className="hint">Drop a .glb and .steps.json here to open another design.</footer>
      </aside>

      <main className="stage">
        {error && <div className="error">{error}</div>}
        {source && (
          <Canvas
            camera={{ fov: 35, near: 0.001, far: 50, position: [0.15, 0.15, 0.2] }}
            dpr={[1, 2]}
            gl={{ preserveDrawingBuffer: true }} // the step tracker captures the expected render
          >
            <color attach="background" args={['#ebe8e4']} />
            <hemisphereLight args={['#ffffff', '#b9b4ae', 1.6]} />
            <directionalLight position={[1, 2, 1.5]} intensity={2.2} />
            <directionalLight position={[-1.5, 1, -1]} intensity={0.8} />
            <Suspense fallback={null}>
              <Bounds fit clip margin={1.3}>
                <Assembly key={source.glbUrl} glbUrl={source.glbUrl} doc={source.doc} step={step} exploded={exploded} />
              </Bounds>
            </Suspense>
            <OrbitControls makeDefault />
          </Canvas>
        )}

        {current && (
          <section className="card">
            <div className="eyebrow">
              Step {step + 1} of {count}
            </div>
            <h2>{current.title}</h2>
            <p>{current.text}</p>
            {current.tools?.length ? (
              <ul className="tools">
                {current.tools.map((t, i) => (
                  <li key={i}>
                    <strong>{t.name}</strong>
                    {t.for && <span> for {t.for}</span>}
                  </li>
                ))}
              </ul>
            ) : null}
            {current.check && (
              <p className="check">
                <span>Camera check</span> {current.check}
              </p>
            )}
            {problem && (
              <div className="problem" role="alert">
                <strong>{problem.problem}</strong>
                <span>{problem.fix}</span>
              </div>
            )}
          </section>
        )}

        {source && <TrackerPanel key={source.glbUrl} doc={source.doc} step={step} setStep={go} onProblem={setProblem} />}

        {source && (
          <nav className="timeline">
            <button onClick={() => go(step - 1)} disabled={step === 0} aria-label="Previous step">
              ‹
            </button>
            <button onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <button onClick={() => go(step + 1)} disabled={step >= count - 1} aria-label="Next step">
              ›
            </button>
            <input
              type="range"
              min={0}
              max={Math.max(count - 1, 0)}
              value={step}
              onChange={(e) => go(Number(e.target.value))}
              aria-label="Step"
            />
            <button className={exploded ? 'active' : ''} onClick={() => setExploded((x) => !x)}>
              Exploded
            </button>
          </nav>
        )}
      </main>
    </div>
  )
}
