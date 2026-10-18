// Who's logged in (mcp-server/physical_studio/users.py). The session token lives in localStorage and
// goes out as `Authorization: Bearer sess_...` on every API call (api.ts headers()). Components
// follow the signed-in user with useUser(), and openLogin() shows the login dialog from anywhere.
import { useEffect, useState } from 'react'

export interface User {
  id: string
  email: string
  name: string
  guest?: boolean // guest mode: no email or password yet
}

const TOKEN = 'physical-studio:session'
const USER = 'physical-studio:user'
const EVENT = 'physical-studio:auth' // fired when someone logs in or out
const OPEN = 'physical-studio:open-login'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function authToken(): string | null {
  return read(TOKEN)
}

export function currentUser(): User | null {
  try {
    return JSON.parse(read(USER) ?? 'null') as User | null
  } catch {
    return null
  }
}

export function setSession(token: string | null, user: User | null) {
  try {
    if (token && user) {
      localStorage.setItem(TOKEN, token)
      localStorage.setItem(USER, JSON.stringify(user))
    } else {
      localStorage.removeItem(TOKEN)
      localStorage.removeItem(USER)
    }
  } catch {
    // storage blocked: the session lasts until the page is closed
  }
  window.dispatchEvent(new Event(EVENT))
}

export function useUser(): User | null {
  const [user, setUser] = useState(currentUser)
  useEffect(() => {
    const update = () => setUser(currentUser())
    window.addEventListener(EVENT, update)
    window.addEventListener('storage', update) // another tab logged in or out
    return () => {
      window.removeEventListener(EVENT, update)
      window.removeEventListener('storage', update)
    }
  }, [])
  return user
}

/** Opens the login dialog (rendered once by the header). */
export function openLogin(mode: 'login' | 'signup' = 'login') {
  window.dispatchEvent(new CustomEvent(OPEN, { detail: mode }))
}

export function onOpenLogin(handler: (mode: 'login' | 'signup') => void): () => void {
  const listener = (e: Event) => handler(((e as CustomEvent).detail as 'login' | 'signup') ?? 'login')
  window.addEventListener(OPEN, listener)
  return () => window.removeEventListener(OPEN, listener)
}
