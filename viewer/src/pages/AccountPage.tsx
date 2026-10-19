// Your account (/account): download everything stored about you, or delete the account and the builds
// it owns (users.py export/delete). The privacy page promises both.
import { useState } from 'react'
import { deleteAccount, exportMyData } from '../api'
import { openLogin, setSession, useUser } from '../auth'
import { Link, ProgressHeader } from '../components/ProgressHeader'
import { navigate } from '../router'
import './DescribePage.css'

export function AccountPage() {
  const user = useUser()
  return (
    <div className="page">
      <ProgressHeader />
      <main className="page-body">
        <div className="describe-page">
          <section className="describe-main legal">
            <h1>Your data and account</h1>
            {user ? (
              <>
                <p>
                  Signed in as <strong>{user.guest ? 'a guest' : user.email}</strong>.
                </p>
                <Download />
                <Delete guest={!!user.guest} />
              </>
            ) : (
              <p>
                <button type="button" className="pill-button" onClick={() => openLogin('login')}>
                  Log in
                </button>{' '}
                to download or delete your data.
              </p>
            )}
            <p className="muted">
              What we keep and why: <Link to="/privacy">Privacy</Link>.
            </p>
          </section>
        </div>
      </main>
    </div>
  )
}

function Download() {
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="commit-box account-box">
      <h2>Download your data</h2>
      <p className="muted">Your account details, saved projects and the builds you started, with their steps and commits, as one JSON file.</p>
      <div className="commit-row">
        <button
          type="button"
          onClick={() => {
            setError(null)
            exportMyData().then(
              (data) => {
                const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
                const a = document.createElement('a')
                a.href = url
                a.download = 'physical-studio-data.json'
                a.click()
                setTimeout(() => URL.revokeObjectURL(url), 1000)
              },
              (e) => setError(e instanceof Error ? e.message : String(e)),
            )
          }}
        >
          Download my data
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}

function Delete({ guest }: { guest: boolean }) {
  const [sure, setSure] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <form
      className="commit-box account-box danger"
      onSubmit={(e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        deleteAccount(password).then(
          () => {
            setSession(null, null)
            navigate('/')
          },
          (err) => {
            setError(err instanceof Error ? err.message : String(err))
            setBusy(false)
          },
        )
      }}
    >
      <h2>Delete your account</h2>
      <p className="muted">
        This deletes your account, your saved projects, your uploaded parts and every build you started, with its
        photos. It can't be undone. Ready-made guides you copied are deleted too; the originals stay.
      </p>
      <label className="account-check">
        <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} /> I understand this can't be
        undone
      </label>
      {!guest && (
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Your password"
          aria-label="Your password"
          autoComplete="current-password"
        />
      )}
      <div className="commit-row">
        <button type="submit" className="danger" disabled={!sure || busy || (!guest && !password)}>
          {busy ? 'Deleting…' : 'Delete my account'}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </form>
  )
}
