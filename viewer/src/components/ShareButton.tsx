// Copies a link to this project. Guides and builds are already open to anyone with their link;
// a shared build is view-only for everyone but the person who started it.
import { useState } from 'react'

export function ShareButton({ className = 'share-button' }: { className?: string }) {
  const [copied, setCopied] = useState(false)
  const url = (() => {
    const u = new URL(location.href)
    u.searchParams.delete('step') // share the project, not the step you happen to be on
    return u.toString()
  })()
  return (
    <button
      type="button"
      className={className}
      title={url}
      onClick={() => {
        void navigator.clipboard?.writeText(url).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1800)
        })
      }}
    >
      {copied ? 'Link copied' : 'Share'}
    </button>
  )
}
