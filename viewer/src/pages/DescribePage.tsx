// Screen 1 · Describe the project. Owner: Kelly (huddle task 8cf1504c). Mockup: docs/product-vision.html.
// Prompt box + examples -> startDesign(prompt) -> navigate(`/design/${id}`); parts library from listParts().
import { ProgressHeader } from '../components/ProgressHeader'

export function DescribePage() {
  return (
    <div className="page">
      <ProgressHeader active={1} />
      <main className="page-body">
        <h1>What do you want to build?</h1>
        <p>Screen 1 is coming soon.</p>
      </main>
    </div>
  )
}
