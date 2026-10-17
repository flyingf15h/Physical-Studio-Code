// Screen 5 · Print and share. Owner: Kelly (huddle task 79ec98a2). Mockup: docs/product-vision.html.
// Reads ?design=out/<id>: <design>/design.steps.json (its `print` block has sizes, grams, minutes and
// file names), <design>/design-base.stl, design-lid.stl, design.step.
import { ProgressHeader } from '../components/ProgressHeader'

export function PrintPage() {
  return (
    <div className="page">
      <ProgressHeader active={5} />
      <main className="page-body">
        <h1>Print it, then share it</h1>
        <p>Screen 5 is coming soon.</p>
      </main>
    </div>
  )
}
