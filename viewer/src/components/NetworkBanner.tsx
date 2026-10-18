// Shown when requests to the server fail at the network level (src/network.ts).
import { useEffect, useState } from 'react'
import { backupUrl, onUnreachable } from '../network'
import './NetworkBanner.css'

export function NetworkBanner() {
  const [shown, setShown] = useState(false)
  useEffect(() => onUnreachable(() => setShown(true)), [])
  if (!shown) return null
  const backup = backupUrl()
  return (
    <div className="network-banner" role="alert">
      <span>
        <strong>Your network is blocking Physical Studio's server,</strong> so nothing loads or saves.{' '}
        {backup ? 'The same site works on our other address.' : 'Try another network, or a phone hotspot.'}
      </span>
      {backup && (
        <a className="network-go" href={backup}>
          Open it there
        </a>
      )}
      <button type="button" aria-label="Dismiss" onClick={() => setShown(false)}>
        ×
      </button>
    </div>
  )
}
