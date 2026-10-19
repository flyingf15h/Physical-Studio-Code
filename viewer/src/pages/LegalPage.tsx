// Terms, privacy and safety (/terms, /privacy, /safety), linked from the dashboard footer. Plain-language
// starting points written for the current site; have them checked before taking payments.
import { Link, ProgressHeader } from '../components/ProgressHeader'
import type { LegalDoc } from '../router'
import './DescribePage.css'

const UPDATED = 'October 19, 2026'

export function LegalPage({ doc }: { doc: LegalDoc }) {
  return (
    <div className="page">
      <ProgressHeader />
      <main className="page-body">
        <div className="describe-page">
          <section className="describe-main legal">
            {doc === 'terms' ? <Terms /> : doc === 'privacy' ? <Privacy /> : <Safety />}
            <p className="muted">Last updated {UPDATED}.</p>
            <LegalLinks />
          </section>
        </div>
      </main>
    </div>
  )
}

export function LegalLinks() {
  return (
    <nav className="legal-links" aria-label="Legal">
      <Link to="/safety">Safety</Link> · <Link to="/terms">Terms</Link> · <Link to="/privacy">Privacy</Link>
    </nav>
  )
}

function Safety() {
  return (
    <>
      <h1>Safety</h1>
      <p>
        Physical Studio's guides are written by AI from a parts library with real dimensions, and checked by
        software for common wiring mistakes. They can still be wrong. Read each step before you do it, and stop
        if something doesn't match your parts.
      </p>
      <h2>Before you build</h2>
      <ul>
        <li>Unplug the board (USB and any other power) before you add, move or remove parts or wires.</li>
        <li>Use the resistor a guide asks for. An LED without one can burn out the LED or the board's pin.</li>
        <li>Check polarity: LEDs, electrolytic capacitors, diodes and battery packs only work one way round.</li>
        <li>If anything gets hot, smells or smokes, unplug it straight away and check your wiring.</li>
        <li>Never connect a guide's circuit to mains (wall) power. Use USB, batteries or a low-voltage supply.</li>
        <li>Lithium batteries can catch fire if they're shorted, punctured or charged wrongly. Use a proper charger.</li>
        <li>Wear eye protection when you cut wire or leads, and let a soldering iron cool on its stand.</li>
        <li>Children should build with an adult nearby. Small parts are a choking hazard.</li>
      </ul>
      <h2>Found a mistake?</h2>
      <p>
        Use <strong>Something wrong with this step?</strong> under the step. A person reads every report and
        fixes the guide.
      </p>
    </>
  )
}

function Terms() {
  return (
    <>
      <h1>Terms of use</h1>
      <p>By using Physical Studio you agree to these terms. If you don't agree, please don't use the site.</p>
      <h2>What the service is</h2>
      <p>
        Physical Studio turns a description of a project into a step-by-step build guide, and can check photos of
        your work against each step. Guides and photo checks are made by AI and can be wrong.
      </p>
      <h2>Your responsibility</h2>
      <ul>
        <li>
          You build at your own risk. Follow the <Link to="/safety">safety guidelines</Link>, and check each step
          against your parts' datasheets.
        </li>
        <li>
          We aren't responsible for damaged parts, boards, tools or property, or for injury, from following a
          guide or a photo check, to the extent the law allows.
        </li>
        <li>Don't use the service to design anything dangerous or illegal, or to overload or attack it.</li>
        <li>Keep your account password and personal AI keys private. You're responsible for what they're used for.</li>
      </ul>
      <h2>Your content</h2>
      <p>
        You keep the rights to the descriptions, photos and parts lists you upload. You let us store and process
        them to run the service (making your guides, checking your photos, and showing shared builds to the people
        you share them with). Only upload photos you have the right to share, and keep people's faces out of them.
      </p>
      <h2>The service</h2>
      <p>
        The service is provided as it is, without warranties. Features can change, and we may remove builds or
        accounts that break these terms. We'll update these terms here when they change.
      </p>
    </>
  )
}

function Privacy() {
  return (
    <>
      <h1>Privacy</h1>
      <h2>What we collect</h2>
      <ul>
        <li>
          <strong>What you enter:</strong> project descriptions, parts lists, bench photos and step photos, BOM
          files, and reports about wrong steps.
        </li>
        <li>
          <strong>Accounts:</strong> your email and name. Passwords are stored only as salted hashes. Guest mode
          needs neither.
        </li>
        <li>
          <strong>Technical data:</strong> your IP address, used only to limit how many builds and reports one
          network can start, and kept in memory for about an hour.
        </li>
        <li>
          <strong>In your browser:</strong> your session, the projects you've opened and your personal AI key are
          kept in your browser's local storage, not in cookies. There are no ads or tracking scripts.
        </li>
      </ul>
      <h2>Who processes it</h2>
      <p>
        To make guides and check photos, your descriptions and photos are sent to AI providers: Google (Gemini),
        OpenAI and DeepSeek. They process them under their own API terms. The site runs on a server hosted by
        Vultr in Toronto, Canada. We don't sell your data.
      </p>
      <h2>Links to shops</h2>
      <p>
        The <strong>Find it</strong> links in a guide's parts list open a search on that shop. Some may be
        affiliate links: if you buy through one, we may earn a small commission at no cost to you.
      </p>
      <h2>Keeping and deleting data</h2>
      <p>
        Builds and photos are kept so you can come back to them. Anyone with a build's link can open it, so only
        share links you mean to. To have your account, builds or photos deleted, contact the team and we'll
        remove them.
      </p>
    </>
  )
}
