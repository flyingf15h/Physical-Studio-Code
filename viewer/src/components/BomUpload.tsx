// Upload a bill of materials (mcp-server/physical_studio/boms.py): a .csv/.tsv file or a pasted table
// goes to POST /api/bom, then GET /api/bom/<id> is polled every 2 s while the server looks each row
// up online and adds it to the user's library. onDone runs once the job is done so the list refreshes.
import { useEffect, useRef, useState } from 'react'
import { authToken, openLogin, useUser } from '../auth'
import './BomUpload.css'

interface BomRow {
  name: string
  link: string
  price: string | number | null
  quantity: number | null
  status: 'looking' | 'added' | 'failed'
  part_id?: string
  size?: string
  error?: string
}

interface BomJob {
  id: string
  status: 'working' | 'done'
  rows: BomRow[]
}

async function bomCall<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${authToken() ?? ''}`,
    },
  })
  const body = await res.json().catch(() => null)
  if (res.status === 401) throw new Error(body?.error ?? 'Your session ended. Log in again.')
  if (!res.ok) throw new Error(body?.error ?? `${url}: ${res.status}`)
  if (body === null) throw new Error(`${url}: the server didn't answer with JSON`)
  return body as T
}

const STATUS_TEXT: Record<BomRow['status'], string> = { looking: 'looking…', added: 'added', failed: 'failed' }

export function BomUpload({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const user = useUser()
  const [text, setText] = useState('')
  const [fileName, setFileName] = useState<string | null>(null)
  const [job, setJob] = useState<BomJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const onDoneRef = useRef(onDone)
  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])

  const jobId = job?.id
  const working = job?.status === 'working'
  useEffect(() => {
    if (!jobId || !working) return
    let live = true
    let timer: number | undefined
    const poll = () => {
      bomCall<BomJob>(`/api/bom/${encodeURIComponent(jobId)}`)
        .then((next) => {
          if (!live) return
          setJob(next)
          if (next.status === 'done') onDoneRef.current()
          else timer = window.setTimeout(poll, 2000)
        })
        .catch((e) => {
          if (!live) return
          setError(e instanceof Error ? e.message : String(e))
          setJob((j) => (j ? { ...j, status: 'done' } : j))
        })
    }
    timer = window.setTimeout(poll, 2000)
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [jobId, working])

  const pickFile = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    try {
      setText(await file.text())
      setFileName(file.name)
    } catch {
      setError(`Couldn't read ${file.name}.`)
    }
  }

  const upload = async () => {
    if (!text.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await bomCall<{ id: string }>('/api/bom', {
        method: 'POST',
        body: JSON.stringify({ text }),
      })
      setJob({ id, status: 'working', rows: [] })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setJob(null)
    setText('')
    setFileName(null)
    setError(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  if (!user || !authToken()) {
    return (
      <div className="bom-upload">
        <button type="button" className="bom-login" onClick={() => openLogin()}>
          Log in to upload a BOM
        </button>
        <button type="button" className="bom-link" onClick={onClose}>
          Cancel
        </button>
      </div>
    )
  }

  if (job) {
    const added = job.rows.filter((r) => r.status === 'added').length
    const failed = job.rows.filter((r) => r.status === 'failed').length
    return (
      <div className="bom-upload">
        <p className="bom-summary" aria-live="polite">
          {working
            ? `Looking up ${job.rows.length || 'the'} part${job.rows.length === 1 ? '' : 's'} online…`
            : `Done: ${added} added${failed ? `, ${failed} failed` : ''}.`}
        </p>
        {job.rows.length > 0 && (
          <ul className="bom-rows">
            {job.rows.map((row, i) => (
              <li key={i} className={`bom-row ${row.status}`}>
                <span className="bom-row-name" title={row.link || undefined}>
                  {row.quantity && row.quantity > 1 ? `${row.quantity} × ` : ''}
                  {row.name}
                </span>
                <span className="bom-row-status">{STATUS_TEXT[row.status] ?? row.status}</span>
                {row.status === 'added' && row.size && <span className="bom-row-note">{row.size}</span>}
                {row.status === 'failed' && row.error && <span className="bom-row-note">{row.error}</span>}
              </li>
            ))}
          </ul>
        )}
        {error && <p className="bom-error">{error}</p>}
        {!working && (
          <div className="bom-actions">
            <button type="button" className="bom-link" onClick={reset}>
              Upload another
            </button>
            <button type="button" className="bom-link" onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <form
      className="bom-upload"
      onSubmit={(e) => {
        e.preventDefault()
        void upload()
      }}
    >
      <label className="bom-file">
        <span>Bill of materials (.csv or .tsv)</span>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain"
          onChange={(e) => void pickFile(e.target.files?.[0])}
        />
      </label>
      <textarea
        className="bom-text"
        value={text}
        rows={5}
        placeholder={'or paste a table, e.g.\nName, Link, Price (CAD)\nArduino Uno, https://…, 32.00'}
        aria-label="or paste a table"
        onChange={(e) => {
          setText(e.target.value)
          setFileName(null)
        }}
      />
      {fileName && <p className="bom-hint">Read {fileName}. You can edit it above before uploading.</p>}
      {error && <p className="bom-error">{error}</p>}
      <div className="bom-actions">
        <button type="submit" className="bom-submit" disabled={!text.trim() || busy}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
        <button type="button" className="bom-link" onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  )
}
