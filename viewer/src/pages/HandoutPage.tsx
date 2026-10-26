// A build guide as a printable handout, for classrooms and tutoring sessions where every student (or
// group) works from paper: a parts checklist, each step with its numbered picture and holes, the
// tests to run along the way, the sketch, and a "when it doesn't work" list. /build/<id>/handout;
// the build page links here. On screen it is a plain page with a Print button; the print styles drop
// the button and keep each step on one page.
import { useEffect, useState } from 'react'
import { getBuild, type Build, type BuildStep } from '../api'
import './HandoutPage.css'

// What goes wrong most on a student's first builds, in the order worth checking.
const TROUBLESHOOTING = [
  'Unplug the USB cable before you move any part or wire, and plug it back in only when the step is done.',
  'An LED that stays dark is usually in backwards: the longer leg goes toward the Arduino pin, the shorter leg (flat side) toward ground.',
  'Push every leg and wire end all the way into its hole. If a row still does nothing, move the part one row along: old breadboards get worn holes.',
  "Parts past the middle of the board get no power: your breadboard's power rails are probably split halfway. Bridge each rail across the gap with a short wire.",
  "A sensor or display that gets warm or does nothing: unplug USB at once and check that its VCC and GND pins match the labels printed on the board, not just the picture.",
  'The upload fails: in the Arduino IDE pick Tools → Board → Arduino Uno (or your board) and the right Port, and try another USB cable; some only charge.',
  'A button that always reads pressed, or never does: turn it a quarter turn so its legs straddle the centre gap the way the picture shows.',
]

function holesOf(step: BuildStep): { n: number | null; what: string; hole: string; where: string }[] {
  if (step.markers?.length) return step.markers.map(([n, what, where, hole]) => ({ n, what, hole, where }))
  return step.placements.map((p) => ({ n: null, what: p.what, hole: p.hole, where: p.where }))
}

export function HandoutPage({ buildId }: { buildId: string }) {
  const [build, setBuild] = useState<Build | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    getBuild(buildId).then(setBuild, (e: Error) => setError(e.message))
  }, [buildId])
  const plan = build?.plan
  useEffect(() => {
    if (plan) document.title = `${plan.title} · handout · Physical Studio`
  }, [plan])
  if (error) return <main className="handout"><p className="handout-note">This guide couldn't be loaded: {error}</p></main>
  if (!build) return <main className="handout"><p className="handout-note">Loading the guide…</p></main>
  if (!plan) return <main className="handout"><p className="handout-note">This guide isn't ready yet. Open it again once it has finished.</p></main>

  const link = `${location.origin}/build/${build.id}`
  const tests = new Map((plan.tests ?? []).map((t) => [t.after_step, t]))
  return (
    <main className="handout">
      <div className="handout-actions">
        <a href={`/build/${build.id}`}>← Back to the guide</a>
        <button type="button" onClick={() => window.print()}>Print</button>
      </div>

      <header className="handout-head">
        <h1>{plan.title}</h1>
        <p>{plan.summary}</p>
        <dl className="handout-meta">
          <div><dt>Name</dt><dd /></div>
          <div><dt>Date</dt><dd /></div>
          <div><dt>Online guide</dt><dd className="handout-link">{link}</dd></div>
        </dl>
      </header>

      <section className="handout-section">
        <h2>Parts checklist</h2>
        <p className="handout-note">Tick each part off as you collect it, before you start building.</p>
        <table className="handout-parts">
          <thead>
            <tr><th aria-label="Got it" /><th>Qty</th><th>Part</th><th>What it's for</th></tr>
          </thead>
          <tbody>
            {plan.parts.map((p, i) => (
              <tr key={i}>
                <td><span className="handout-box" aria-hidden="true" /></td>
                <td>{p.quantity}</td>
                <td>{p.name}</td>
                <td>{p.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {plan.safety.length > 0 && (
        <section className="handout-section">
          <h2>Before you start</h2>
          <ul>{plan.safety.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </section>
      )}

      <section className="handout-section">
        <h2>Steps</h2>
        {plan.steps.map((step) => {
          const test = tests.get(step.number)
          return (
            <article key={step.number} className="handout-step">
              <h3><span className="handout-num">{step.number}</span>{step.title}</h3>
              {step.picture && <img src={step.picture} alt={`Step ${step.number}: ${step.title}`} />}
              <p>{step.instruction}</p>
              {holesOf(step).length > 0 && (
                <ol className="handout-holes">
                  {holesOf(step).map((h, i) => (
                    <li key={i}>
                      {h.n !== null && <span className="handout-badge">{h.n}</span>}
                      <strong>{h.what}</strong> → {h.hole.replace(/^pin:/, 'pin ')}
                      {h.where && <span className="handout-where"> ({h.where})</span>}
                    </li>
                  ))}
                </ol>
              )}
              <p className="handout-check"><span className="handout-box" aria-hidden="true" /> <strong>Check:</strong> {step.check}</p>
              {test && (
                <div className="handout-test">
                  <strong>Test now: {test.title}.</strong> Upload the test sketch from the online guide. You should see: {test.expect}
                  <div><strong>If it doesn't work:</strong> {test.if_not}</div>
                </div>
              )}
            </article>
          )
        })}
      </section>

      <section className="handout-section handout-done">
        <h2>When it's finished</h2>
        <p>{plan.final_result}</p>
        <p className="handout-check"><span className="handout-box" aria-hidden="true" /> Checked by: ____________________</p>
      </section>

      <section className="handout-section">
        <h2>When it doesn't work</h2>
        <ol>{TROUBLESHOOTING.map((t, i) => <li key={i}>{t}</li>)}</ol>
      </section>

      {plan.code && (
        <section className="handout-section handout-code">
          <h2>The Arduino sketch</h2>
          <p className="handout-note">Copy it from the online guide rather than typing it: {link}</p>
          <pre>{plan.code}</pre>
        </section>
      )}
    </main>
  )
}
