// Some networks (school and venue filters) block the new physicalstudio.work domain: the page can
// still come from the browser's cache or over HTTP/3, but requests to the server get reset, so
// buttons seem to do nothing. Requests that never reach the server report it here, and
// NetworkBanner offers the same page on the server's other address.

const EVENT = 'physical-studio:unreachable'
export const BACKUP_HOST = '155-138-154-8.sslip.io'

/** fetch() that announces when the server can't be reached at all (not an HTTP error). */
export async function reach(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch {
    window.dispatchEvent(new Event(EVENT))
    throw new Error("Can't reach the Physical Studio server from this network.")
  }
}

export function onUnreachable(handler: () => void): () => void {
  window.addEventListener(EVENT, handler)
  return () => window.removeEventListener(EVENT, handler)
}

/** This page on the backup address, or null when we're not on the blocked domain. */
export function backupUrl(): string | null {
  if (!/(^|\.)physicalstudio\.work$/.test(location.hostname)) return null
  const u = new URL(location.href)
  u.hostname = BACKUP_HOST
  return u.toString()
}
