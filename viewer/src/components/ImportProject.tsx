// "Import a project" under the Dashboard's prompt: paste a link to an existing project (a GitHub repository
// first; Printables, Thingiverse and Instructables pages work too) and the server reads what's there (README,
// parts list, wiring tables, firmware pin definitions, CAD files) and writes its build guide
// (POST /api/build/import, mcp-server/physical_studio/bench/importer.py). Opens it at /build/<id>, like Design it.
import { useState } from 'react'
import { importProject } from '../api'
import { navigate, withParams } from '../router'
import './ImportProject.css'

function asLink(text: string): string | null {
  try {
    const url = new URL(text.trim())
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

export function ImportProject({ code }: { code?: string | null }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const link = asLink(url)

  const submit = async () => {
    if (!link || busy) return
    setBusy(true)
    setError(null)
    try {
      const { id } = await importProject(link)
      navigate(withParams(`/build/${id}`, { code }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <form
      className="import-project"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <label className="import-project-label" htmlFor="import-project-url">
        Import a project
      </label>
      <span className="import-project-hint">A GitHub repository, or a Printables, Thingiverse or Instructables page</span>
      <div className="import-project-row">
        <input
          id="import-project-url"
          type="url"
          value={url}
          placeholder="https://github.com/you/your-project"
          onChange={(e) => {
            setUrl(e.target.value)
            setError(null)
          }}
        />
        <button type="submit" className="describe-tool" disabled={!link || busy}>
          {busy ? 'Reading it…' : 'Import'}
        </button>
      </div>
      {error && <p className="describe-error">{error}</p>}
    </form>
  )
}
