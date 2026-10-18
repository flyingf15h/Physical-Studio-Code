// Dashboard (screen 1). Mockup: docs/product-vision.html. "Design it" starts a breadboard build on the
// server's own model keys (Senna's Build helper flow, mcp-server/physical_studio/bench/): the prompt,
// photos of your bench, the parts you have and connections you already know. It moves on to the
// build's page (/build/<id>). The example prompts (Senna's Claude) fill the prompt; picking a part in the
// parts library (Kelly's Claude) adds it to "Parts I have" (PartsInput), where each part is a chip looked up
// in the library. Below: the ready-made guides, and designing with your own AI.
import { useRef, useState } from 'react'
import { startBuild } from '../api'
import { ConnectAI } from '../components/ConnectAI'
import { ExamplePrompts } from '../components/ExamplePrompts'
import { PartsInput } from '../components/PartsInput'
import { PartsLibrary } from '../components/PartsLibrary'
import { ReadyMadeGuides } from '../components/ProjectsList'
import { ProgressHeader } from '../components/ProgressHeader'
import { shrink } from '../images'
import { designParams, navigate, withParams } from '../router'
import './DescribePage.css'

const MIN_CHARS = 3
const MAX_CHARS = 1000
const MAX_IMAGES = 10 // bench photos; same limit as the build API (mcp-server/physical_studio/bench/)
const MAX_LINKS = 5
function asLink(text: string): string | null {
  try {
    const url = new URL(text.trim())
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

export function DescribePage() {
  const [prompt, setPrompt] = useState('')
  const [images, setImages] = useState<string[]>([])
  const [links, setLinks] = useState<string[]>([])
  const [linkDraft, setLinkDraft] = useState<string | null>(null) // null: link field hidden
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [have, setHave] = useState<string[]>([])
  const [known, setKnown] = useState('')
  const box = useRef<HTMLTextAreaElement>(null)
  const filePicker = useRef<HTMLInputElement>(null)
  const { code } = designParams()
  const length = prompt.trim().length
  const ready = length >= MIN_CHARS && length <= MAX_CHARS && !busy

  const fill = (text: string) => {
    setPrompt(text)
    setError(null)
    box.current?.focus()
  }

  const addImages = async (files: Iterable<File>) => {
    const picked = [...files].filter((f) => f.type.startsWith('image/'))
    if (!picked.length) return
    const room = MAX_IMAGES - images.length
    if (room <= 0) return setError(`You can attach up to ${MAX_IMAGES} images.`)
    try {
      const shrunk = await Promise.all(picked.slice(0, room).map(shrink))
      setImages((now) => [...now, ...shrunk].slice(0, MAX_IMAGES))
      setError(
        picked.length > room ? `Only the first ${room} image${room === 1 ? '' : 's'} fit (up to ${MAX_IMAGES}).` : null,
      )
    } catch {
      setError("Couldn't read that image.")
    }
  }

  const addLink = () => {
    const url = asLink(linkDraft ?? '')
    if (!url) return setError('Links need to start with http:// or https://')
    if (links.length >= MAX_LINKS) return setError(`You can add up to ${MAX_LINKS} links.`)
    if (!links.includes(url)) setLinks([...links, url])
    setLinkDraft(null)
    setError(null)
  }

  const submit = async () => {
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      const goal = prompt.trim() + (links.length ? `\nLinks: ${links.join(' ')}` : '')
      const { id } = await startBuild({ goal, have: have.join(', '), known: known.trim(), photos: images })
      navigate(withParams(`/build/${id}`, { code }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <ProgressHeader tab="dashboard" />
      <main className="page-body">
        <div className="describe-page">
          <section className="describe-main">
            <h1>What do you want to build?</h1>
            <p className="describe-lede">
              Say what you want to build and add photos of your bench if you have them. Physical Studio works out what's
              already plugged in, adds the parts you still need, and writes step-by-step instructions with a picture and
              a 3D model for every step. Photograph each step and it checks your work.
            </p>
            <form
              className={`describe-form${dragging ? ' dragging' : ''}`}
              onSubmit={(e) => {
                e.preventDefault()
                void submit()
              }}
              onPaste={(e) => {
                const files = [...e.clipboardData.files]
                if (files.some((f) => f.type.startsWith('image/'))) {
                  e.preventDefault()
                  void addImages(files)
                }
              }}
              onDragOver={(e) => {
                if ([...e.dataTransfer.items].some((i) => i.kind === 'file')) {
                  e.preventDefault()
                  setDragging(true)
                }
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                void addImages(e.dataTransfer.files)
              }}
            >
              <textarea
                ref={box}
                value={prompt}
                maxLength={MAX_CHARS}
                rows={4}
                placeholder="e.g. A traffic light: red, yellow and green LEDs that cycle, and a button that starts a crosswalk cycle."
                aria-label="Describe your project"
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    void submit()
                  }
                }}
              />
              {(images.length > 0 || links.length > 0) && (
                <ul className="describe-attached">
                  {images.map((src, i) => (
                    <li key={src.slice(-32) + i} className="describe-thumb">
                      <img src={src} alt={`Attached image ${i + 1}`} />
                      <button
                        type="button"
                        aria-label={`Remove image ${i + 1}`}
                        onClick={() => setImages(images.filter((_, j) => j !== i))}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                  {links.map((url) => (
                    <li key={url} className="describe-link">
                      <span title={url}>{new URL(url).hostname + new URL(url).pathname.replace(/\/$/, '')}</span>
                      <button
                        type="button"
                        aria-label={`Remove link ${url}`}
                        onClick={() => setLinks(links.filter((l) => l !== url))}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="describe-extra">
                <PartsInput parts={have} onChange={setHave} />
                <textarea
                  value={known}
                  onChange={(e) => setKnown(e.target.value)}
                  maxLength={3000}
                  rows={2}
                  placeholder="Optional: connections you already know, e.g. red LED long leg in e10, wire from pin 9 to a10"
                  aria-label="Connections you already know"
                />
              </div>
              {linkDraft !== null && (
                <div className="describe-linkrow">
                  <input
                    type="url"
                    autoFocus
                    value={linkDraft}
                    placeholder="https://… a product page, datasheet, tutorial or image"
                    aria-label="Link"
                    onChange={(e) => setLinkDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addLink()
                      } else if (e.key === 'Escape') setLinkDraft(null)
                    }}
                  />
                  <button type="button" className="describe-tool" onClick={addLink}>
                    Add
                  </button>
                  <button type="button" className="describe-tool" onClick={() => setLinkDraft(null)}>
                    Cancel
                  </button>
                </div>
              )}
              <div className="describe-actions">
                <button
                  type="button"
                  className="describe-tool"
                  disabled={images.length >= MAX_IMAGES}
                  onClick={() => filePicker.current?.click()}
                >
                  Add bench photos
                </button>
                <button
                  type="button"
                  className="describe-tool"
                  disabled={links.length >= MAX_LINKS || linkDraft !== null}
                  onClick={() => setLinkDraft('')}
                >
                  Add link
                </button>
                <input
                  ref={filePicker}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  multiple
                  hidden
                  onChange={(e) => {
                    if (e.target.files) void addImages(e.target.files)
                    e.target.value = ''
                  }}
                />
                <span className="describe-hint">or paste / drop photos</span>
                <span className="describe-count">
                  {length}/{MAX_CHARS}
                </span>
                <button type="submit" className="describe-go" disabled={!ready}>
                  {busy ? 'Starting…' : 'Design it'}
                </button>
              </div>
              {error && <p className="describe-error">{error}</p>}
            </form>
            <h2 className="describe-sub">Ready-made guides</h2>
            <ReadyMadeGuides />
            <h2 className="describe-sub">Try one</h2>
            <ExamplePrompts onPick={fill} />
            <div className="describe-parts">
              <PartsLibrary onPick={(part) => setHave(have.includes(part.name) ? have : [...have, part.name])} />
            </div>
            <details className="describe-own-ai">
              <summary>Add your own API key</summary>
              <ConnectAI prompt={prompt} setPrompt={fill} onKey={() => {}} />
            </details>
          </section>
        </div>
      </main>
    </div>
  )
}
