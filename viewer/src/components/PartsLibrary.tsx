// Screen 1 parts library panel. Owner: Kelly's Claude (huddle). STUB: replace the body, keep the props.
// Contract: fetch listParts() from ../api; search box; one card per part with name, body size
// (W × D × H mm) and a Measured / Datasheet badge (part.verified); clicking a card calls onPick.
// Styles in PartsLibrary.css, classes prefixed "parts-".
import type { PartSummary } from '../api'

export function PartsLibrary({ onPick }: { onPick?: (part: PartSummary) => void }) {
  void onPick
  return <aside className="parts-library">Parts library</aside>
}
