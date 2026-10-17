// Tiny history-API router; the app has five screens, not worth a dependency.
//   /                         1 Describe
//   /design/<job id>          2 the AI designs it
//   /guide?design=out/<id>    3 Guide + 4 Build (the tracker panel); /?design=... still works
//   /print?design=out/<id>    5 Print and share

import { useEffect, useState } from 'react'

export type Route = { page: 'describe' } | { page: 'design'; jobId: string } | { page: 'guide' } | { page: 'print' }

export function parseRoute(path = location.pathname, search = location.search): Route {
  const job = path.match(/^\/design\/([\w-]+)\/?$/)
  if (job) return { page: 'design', jobId: job[1] }
  if (path.startsWith('/guide')) return { page: 'guide' }
  if (path.startsWith('/print')) return { page: 'print' }
  if (new URLSearchParams(search).has('design')) return { page: 'guide' } // old /?design=... links
  return { page: 'describe' }
}

export function navigate(to: string) {
  history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute())
  useEffect(() => {
    const onChange = () => setRoute(parseRoute())
    window.addEventListener('popstate', onChange)
    return () => window.removeEventListener('popstate', onChange)
  }, [])
  return route
}

/** ?design=out/<id> (or sample) and ?job=<id> carried between screens. */
export function designParams() {
  const q = new URLSearchParams(location.search)
  return { design: q.get('design'), job: q.get('job'), code: q.get('code') }
}

export function withParams(path: string, params: Record<string, string | null | undefined>) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v)
  const s = q.toString()
  return s ? `${path}?${s}` : path
}
