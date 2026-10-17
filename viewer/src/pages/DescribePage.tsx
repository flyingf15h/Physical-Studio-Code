// Screen 1 · Describe the project. Mockup: docs/product-vision.html. The prompt box starts a design
// job and moves on to screen 2; the example prompts (Senna's Claude) and the parts library (Kelly's
// Claude) fill or extend the prompt. Images (upload, paste or drop) and links go along with it.
import { useEffect, useRef, useState } from 'react'
import { listProviders, startDesign, type Provider } from '../api'
import { ExamplePrompts } from '../components/ExamplePrompts'
import { PartsLibrary } from '../components/PartsLibrary'
import { ProgressHeader } from '../components/ProgressHeader'
import { designParams, navigate, withParams } from '../router'
import './DescribePage.css'

const MIN_CHARS = 3
const MAX_CHARS = 1000
const MAX_IMAGES = 4 // same limits as mcp-server/physical_studio/attachments.py
const MAX_LINKS = 5
const MAX_SIDE = 1600 // px; photos are shrunk before upload

/** Image file -> JPEG data URL, longest side at most MAX_SIDE. */
async function shrink(file: Blob): Promise<string> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#fff' // transparent PNGs become white, not black
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvas.toDataURL('image/jpeg', 0.85)
}

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
  const [providers, setProviders] = useState<Provider[]>([])
  const [model, setModel] = useState<string | null>(null) // null: the server default

  useEffect(() => {
    listProviders().then(setProviders, () => setProviders([])) // no picker if it fails
  }, [])
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
      setError(picked.length > room ? `Only the first ${room} image${room === 1 ? '' : 's'} fit (up to ${MAX_IMAGES}).` : null)
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
      const { id } = await startDesign(prompt.trim(), { images, links, ...(model ? { model } : {}) })
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
            Describe a project. Physical Studio CADs the 3D-printable components around real, measured parts, and
            writes a step-by-step assembly guide that follows you as you build.
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
              placeholder="e.g. Traffic light for an Arduino Uno: red, yellow and green LEDs in a column on the lid, a crosswalk button, USB accessible on the side."
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
                    <button type="button" aria-label={`Remove image ${i + 1}`} onClick={() => setImages(images.filter((_, j) => j !== i))}>
                      ×
                    </button>
                  </li>
                ))}
                {links.map((url) => (
                  <li key={url} className="describe-link">
                    <span title={url}>{new URL(url).hostname + new URL(url).pathname.replace(/\/$/, '')}</span>
                    <button type="button" aria-label={`Remove link ${url}`} onClick={() => setLinks(links.filter((l) => l !== url))}>
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
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
                Add image
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
              <span className="describe-hint">or paste / drop an image</span>
              <span className="describe-count">
                {length}/{MAX_CHARS}
              </span>
              {providers.length > 1 && (
                <label className="describe-model">
                  <span>Model</span>
                  <select value={model ?? providers[0].id} onChange={(e) => setModel(e.target.value)}>
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
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
              href={withParams('/guide', { design: 'traffic-light', code })}
              onClick={(e) => {
                e.preventDefault()
                navigate(withParams('/guide', { design: 'traffic-light', code }))
              }}
            >
              finished traffic light guide
            </a>
            .
          </p>
        </section>
        <PartsLibrary onPick={(part) => fill(prompt.trim() ? `${prompt.trim()} ${part.name}` : part.name)} />
      </main>
    </div>
  )
}
