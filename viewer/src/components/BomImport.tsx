// "Upload BOM" in Parts I have: a CSV/TSV file or a pasted shop table. Rows the parts library has come
// back as they are; the others are looked up online and added to your own parts (boms.py). Each row
// then becomes a chip. Guests can do it too: without a session, a guest one starts first.
import { useRef, useState } from 'react'
import { getBom, guestLogIn, uploadBom, type BomRow } from '../api'
import { authToken, setSession } from '../auth'
import { chipFor, PARTS_CHANGED } from '../bom'
import './BomImport.css'

const POLL_MS = 2000

export function BomImport({ onParts, onClose }: { onParts: (chips: string[]) => void; onClose: () => void }) {
  const [text, setText] = useState('')
  const [rows, setRows] = useState<BomRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      if (!authToken()) {
        const { token, user } = await guestLogIn() // keeps the parts you add with you, even as a guest
        setSession(token, user)
      }
      const { id } = await uploadBom(text)
      for (;;) {
        const job = await getBom(id)
        setRows(job.rows)
        if (job.status === 'done') {
          onParts(job.rows.map(chipFor))
          if (job.rows.some((r) => r.status === 'added')) window.dispatchEvent(new Event(PARTS_CHANGED))
          break
        }
        await new Promise((r) => setTimeout(r, POLL_MS))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const label: Record<BomRow['status'], string> = {
    looking: 'Looking it up…',
    in_library: 'In the library',
    added: 'Added to your parts',
    failed: 'Not found',
  }
  return (
    <div className="bom-import" onClick={(e) => e.stopPropagation()}>
      <div className="bom-import-head">
        <strong>Upload your BOM</strong>
        <span className="muted">
          A CSV or a pasted table, one part per row (name, link, price). Parts the library doesn't have are looked up
          and added.
        </span>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder={'Name\tLink\tPrice\nTeensy 4.1\thttps://…\t60.13\n2x VL53L0X TOF Sensor\thttps://…\t7.30'}
        aria-label="Paste your BOM"
        disabled={busy}
      />
      <div className="bom-import-actions">
        <button type="button" className="ghost" disabled={busy} onClick={() => picker.current?.click()}>
          Choose a file
        </button>
        <input
          ref={picker}
          type="file"
          accept=".csv,.tsv,.txt,text/csv,text/plain"
          hidden
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (file) setText((await file.text()).slice(0, 20000))
            e.target.value = ''
          }}
        />
        <span className="spacer" />
        <button type="button" className="ghost" disabled={busy} onClick={onClose}>
          Close
        </button>
        <button type="button" disabled={busy || !text.trim()} onClick={() => void run()}>
          {busy ? 'Adding parts…' : 'Add these parts'}
        </button>
      </div>
      {error && <p className="bom-import-error">{error}</p>}
      {rows && (
        <ul className="bom-import-rows">
          {rows.map((r, i) => (
            <li key={i} className={r.status}>
              <span className="bom-name">
                {r.quantity > 1 ? `${r.quantity} × ` : ''}
                {r.name}
              </span>
              <span className="bom-status">
                {label[r.status]}
                {r.part_name && r.part_name !== r.name ? ` · ${r.part_name}` : ''}
                {r.size ? ` · ${r.size}` : ''}
                {r.status === 'failed' && r.error ? ` · ${r.error}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
