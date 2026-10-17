import { useEffect, useRef, useState } from 'react'
import type { StepsDoc } from '../steps'
import { StepTracker, type Problem, type TrackerStatus, type Verdict } from './session'

const RENDER_SETTLE_MS = 1600 // let the step's fly-in animation finish before capturing the render
const CAPTURE_WIDTH = 768

/** JPEG (base64) of the 3D view once it has settled: the expected result of the step. */
async function captureExpected(): Promise<string | null> {
  await new Promise((r) => setTimeout(r, RENDER_SETTLE_MS))
  const source = document.querySelector<HTMLCanvasElement>('.stage canvas')
  if (!source?.width) return null
  const canvas = document.createElement('canvas')
  canvas.width = CAPTURE_WIDTH
  canvas.height = Math.round((source.height / source.width) * CAPTURE_WIDTH)
  canvas.getContext('2d')!.drawImage(source, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.8).split(',')[1] ?? null
}

interface Props {
  doc: StepsDoc
  step: number
  setStep: (step: number) => void
  onProblem: (problem: Problem | null) => void
}

export function TrackerPanel({ doc, step, setStep, onProblem }: Props) {
  const [status, setStatus] = useState<TrackerStatus>('idle')
  const [detail, setDetail] = useState<string>()
  const [gemini, setGemini] = useState('')
  const [you, setYou] = useState('')
  const [muted, setMuted] = useState(false)
  const [micMuted, setMicMuted] = useState(false)
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const tracker = useRef<StepTracker | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const advancedByGemini = useRef(false)
  const lastObservation = useRef('')
  const stepRef = useRef(step)
  stepRef.current = step

  const start = () => {
    tracker.current?.stop()
    const t = new StepTracker(doc, {
      status: (s, d) => {
        setStatus(s)
        setDetail(d)
        if (s === 'watching' && video.current && t.mediaStream) video.current.srcObject = t.mediaStream
      },
      stepDone: (n, observation) => {
        const current = stepRef.current + 1
        if (n !== current) return { advanced: false, reason: `the builder is on step ${current}, not ${n}` }
        if (current >= doc.steps.length) return { advanced: false, reason: 'that was the last step: the build is done' }
        advancedByGemini.current = true
        lastObservation.current = observation
        setStep(current) // 0-based index of the next step
        return { advanced: true, now_on: current + 1 }
      },
      problem: onProblem,
      verdict: setVerdict,
      transcript: (who, text) => (who === 'gemini' ? setGemini(text) : setYou(text)),
    })
    t.step = stepRef.current
    tracker.current = t
    void t.start(captureExpected)
  }

  const stop = () => {
    tracker.current?.stop()
    tracker.current = null
    onProblem(null)
  }

  // Tell Gemini whenever the builder (or Gemini) changes the step.
  useEffect(() => {
    const t = tracker.current
    if (!t || status !== 'watching' || t.step === step) return
    t.step = step
    const lead = advancedByGemini.current ? `The checker confirmed step ${step} is complete: ${lastObservation.current}. ` : ''
    advancedByGemini.current = false
    void t.announceStep(captureExpected, lead)
  }, [step, status])

  useEffect(() => () => tracker.current?.stop(), [])
  useEffect(() => {
    if (tracker.current) tracker.current.muted = muted
  }, [muted])
  useEffect(() => {
    if (tracker.current) tracker.current.micMuted = micMuted
  }, [micMuted])

  const active = status === 'watching' || status === 'connecting'

  return (
    <section className={`tracker ${active ? 'on' : ''}`}>
      {!active ? (
        <button className="tracker-start" onClick={start}>
          <span className="dot" /> Watch my bench
        </button>
      ) : (
        <>
          <video ref={video} autoPlay muted playsInline />
          <div className="tracker-bar">
            <span className={`status ${status}`}>{status === 'connecting' ? 'Connecting…' : 'Gemini is watching'}</span>
            <button onClick={() => setMicMuted((m) => !m)} aria-pressed={micMuted} title="Microphone">
              {micMuted ? 'Mic off' : 'Mic on'}
            </button>
            <button onClick={() => setMuted((m) => !m)} aria-pressed={muted} title="Voice">
              {muted ? 'Voice off' : 'Voice on'}
            </button>
            <button onClick={stop}>Stop</button>
          </div>
          {you && <p className="line you">{you}</p>}
          {gemini && <p className="line gemini">{gemini}</p>}
          {verdict && (
            <p className="line verdict">
              Checker: {verdict.status.replace('_', ' ')} · {verdict.observation}
            </p>
          )}
        </>
      )}
      {status === 'error' && detail && <p className="tracker-error">{detail}</p>}
    </section>
  )
}
