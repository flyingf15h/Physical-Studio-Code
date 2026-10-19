// The header's account corner: "Log in" (opens the dialog) or your name with a log-out menu. The
// dialog is rendered here once, and anything can open it with openLogin() (src/auth.ts).
import { useEffect, useState } from 'react'
import { guestLogIn, logIn, logOut, signUp } from '../api'
import { onOpenLogin, setSession, useUser } from '../auth'
import { navigate } from '../router'
import './Account.css'

function Dialog({
  mode,
  setMode,
  close,
}: {
  mode: 'login' | 'signup'
  setMode: (m: 'login' | 'signup') => void
  close: () => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const { token, user } = mode === 'signup' ? await signUp(email, password, name) : await logIn(email, password)
      setSession(token, user)
      close()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="account-backdrop" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <form
        className="account-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-title"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <h2 id="account-title">{mode === 'signup' ? 'Create your account' : 'Log in to Physical Studio'}</h2>
        <p className="account-lede">
          Save your projects to your account, share them by link, and upload your parts list.
        </p>
        {mode === 'signup' && (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={60} />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            minLength={mode === 'signup' ? 8 : undefined}
            required
          />
        </label>
        {mode === 'signup' && <span className="account-hint">At least 8 characters.</span>}
        {error && <p className="account-error">{error}</p>}
        <button type="submit" className="account-go" disabled={busy}>
          {busy ? 'One moment…' : mode === 'signup' ? 'Create account' : 'Log in'}
        </button>
        <button
          type="button"
          className="account-guest"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            guestLogIn().then(
              ({ token, user }) => {
                setSession(token, user)
                close()
              },
              (e) => {
                setError(e instanceof Error ? e.message : String(e))
                setBusy(false)
              },
            )
          }}
        >
          Continue as guest
        </button>
        <p className="account-switch">
          {mode === 'signup' ? 'Already have an account?' : 'New to Physical Studio?'}{' '}
          <button type="button" onClick={() => setMode(mode === 'signup' ? 'login' : 'signup')}>
            {mode === 'signup' ? 'Log in' : 'Create an account'}
          </button>
        </p>
      </form>
    </div>
  )
}

export function Account() {
  const user = useUser()
  const [mode, setMode] = useState<'login' | 'signup' | null>(null)
  const [menu, setMenu] = useState(false)
  useEffect(() => onOpenLogin(setMode), [])

  return (
    <div className="account">
      {user ? (
        <>
          <button type="button" className="account-me" onClick={() => setMenu(!menu)} aria-expanded={menu}>
            <span className="account-avatar">{user.name.slice(0, 1).toUpperCase()}</span>
            {user.name}
          </button>
          {menu && (
            <div className="account-menu">
              {user.guest ? (
                <>
                  <span>You're in guest mode. Create an account to keep your work on every device.</span>
                  <button
                    type="button"
                    className="account-primary"
                    onClick={() => {
                      setMode('signup')
                      setMenu(false)
                    }}
                  >
                    Create an account
                  </button>
                </>
              ) : (
                <span>{user.email}</span>
              )}
              <a
                href="/account"
                onClick={(e) => {
                  e.preventDefault()
                  setMenu(false)
                  navigate('/account')
                }}
              >
                Your data and account
              </a>
              <button
                type="button"
                onClick={() => {
                  void logOut().catch(() => {})
                  setSession(null, null)
                  setMenu(false)
                }}
              >
                {user.guest ? 'Leave guest mode' : 'Log out'}
              </button>
            </div>
          )}
        </>
      ) : (
        <button type="button" className="account-login" onClick={() => setMode('login')}>
          Log in
        </button>
      )}
      {mode && <Dialog mode={mode} setMode={setMode} close={() => setMode(null)} />}
    </div>
  )
}
