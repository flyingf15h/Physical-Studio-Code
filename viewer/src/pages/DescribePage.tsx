// Screen 1 · Describe the project. Mockup: docs/product-vision.html. The prompt box starts a design
// job and moves on to screen 2; the example prompts (Senna's Claude) and the parts library (Kelly's
// Claude) fill or extend the prompt.
import { useRef, useState } from 'react'
import { startDesign } from '../api'
import { ExamplePrompts } from '../components/ExamplePrompts'
import { PartsLibrary } from '../components/PartsLibrary'
import { ProgressHeader } from '../components/ProgressHeader'
import { designParams, navigate, withParams } from '../router'
import './DescribePage.css'

const MIN_CHARS = 3
const MAX_CHARS = 1000

export function DescribePage() {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const box = useRef<HTMLTextAreaElement>(null)
  const { code } = designParams()
  const length = prompt.trim().length
  const ready = length >= MIN_CHARS && length <= MAX_CHARS && !busy

  const fill = (text: string) => {
    setPrompt(text)
    setError(null)
    box.current?.focus()
  }

  const submit = async () => {
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await startDesign(prompt.trim())
      navigate(withParams(`/design/${id}`, { code }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <ProgressHeader active={1} />
      <main className="page-body describe-page">
        <section className="describe-main">
          <h1>What do you want to build?</h1>
          <p className="describe-lede">
            Describe a project. The AI designs a 3D-printable case around real, measured parts, checks that
            everything fits, and writes a step-by-step assembly guide that a camera checks as you build.
          </p>
          <form
            className="describe-form"
            onSubmit={(e) => {
              e.preventDefault()
              void submit()
            }}
          >
            <textarea
              ref={box}
              value={prompt}
              maxLength={MAX_CHARS}
              rows={4}
              placeholder="e.g. Simon game for an Arduino Uno, 4 colored buttons with LEDs, buzzer, USB accessible on the side."
              aria-label="Describe your project"
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  void submit()
                }
              }}
            />
            <div className="describe-actions">
              <span className="describe-count">
                {length}/{MAX_CHARS}
              </span>
              <button type="submit" className="describe-go" disabled={!ready}>
                {busy ? 'Starting…' : 'Design it'}
              </button>
            </div>
            {error && <p className="describe-error">{error}</p>}
          </form>
          <h2 className="describe-sub">Try one</h2>
          <ExamplePrompts onPick={fill} />
          <p className="describe-sample">
            Or open the{' '}
            <a
              href={withParams('/guide', { design: 'simon', code })}
              onClick={(e) => {
                e.preventDefault()
                navigate(withParams('/guide', { design: 'simon', code }))
              }}
            >
              finished Simon game guide
            </a>
            .
          </p>
        </section>
        <PartsLibrary onPick={(part) => fill(prompt.trim() ? `${prompt.trim()} ${part.name}` : part.name)} />
      </main>
    </div>
  )
}
