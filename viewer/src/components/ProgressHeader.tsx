import type { ReactNode } from 'react'
import { designParams, navigate, withParams } from '../router'
import { Account } from './Account'
import './ProgressHeader.css'

const STEPS = ['Describe', 'Design', 'Guide', 'Build', 'Print'] as const

const TABS = [
  { id: 'dashboard', label: 'Dashboard', path: '/' },
  { id: 'projects', label: 'Your projects', path: '/projects' },
] as const

interface Props {
  /** The project screen you're on; the 1-to-5 steps only show once a project has started. */
  active?: 1 | 2 | 3 | 4 | 5
  /** The tab you're on, outside a project. */
  tab?: (typeof TABS)[number]['id']
  /** Overrides for links when the page knows more than the URL (e.g. the design page). */
  design?: string | null
  job?: string | null
  /** A breadboard build (/build/<id>): Design, Guide and Build all open its page; there is no Print. */
  build?: string
}

function Link({ to, className, children }: { to: string; className?: string; children: ReactNode }) {
  return (
    <a
      className={className}
      href={to}
      onClick={(e) => {
        e.preventDefault()
        navigate(to)
      }}
    >
      {children}
    </a>
  )
}

/** Dashboard · Your projects tabs on every screen, plus "1 Describe ✓ · 2 Design · ..." inside a project. */
export function ProgressHeader({ active, tab, design, job, build }: Props) {
  const params = designParams()
  const d = design ?? params.design
  const j = job ?? params.job
  const code = params.code
  const buildHref = build ? withParams(`/build/${build}`, { code }) : null
  const href: Record<number, string | null> = build
    ? { 1: withParams('/', { code }), 2: buildHref, 3: buildHref, 4: buildHref, 5: null }
    : {
        1: withParams('/', { code }),
        2: j ? withParams(`/design/${j}`, { code }) : null,
        3: d ? withParams('/guide', { design: d, job: j, code }) : null,
        4: d ? withParams('/guide', { design: d, job: j, code }) : null,
        5: d ? withParams('/print', { design: d, job: j, code }) : null,
      }
  return (
    <header className="progress-header">
      <Link className="brand" to={href[1]!}>
        <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 3 28 9.5v13L16 29 4 22.5v-13Z" fill="#0b7f8f" />
          <path d="M16 3 28 9.5 16 16 4 9.5Z" fill="#3cc4d4" />
          <path d="M16 16v13L4 22.5v-13Z" fill="#0f9fb3" />
          <path
            d="m10 12.7 6 3.3 6-3.3"
            fill="none"
            stroke="#fff"
            strokeWidth="1.6"
            strokeLinecap="round"
            opacity=".85"
          />
        </svg>
        Physical Studio
      </Link>
      <nav className="tabs">
        {TABS.map((t) => (
          <Link key={t.id} to={withParams(t.path, { code })} className={t.id === tab ? 'active' : ''}>
            {t.label}
          </Link>
        ))}
      </nav>
      {active && (
        <ol>
          {STEPS.map((label, i) => {
            const n = i + 1
            const state = n < active ? 'done' : n === active ? 'active' : 'todo'
            const to = href[n]
            return (
              <li key={label} className={state}>
                {to && n !== active ? (
                  <a
                    href={to}
                    onClick={(e) => {
                      e.preventDefault()
                      navigate(to)
                    }}
                  >
                    <span className="num">{state === 'done' ? '✓' : n}</span>
                    {label}
                  </a>
                ) : (
                  <span aria-current={n === active ? 'step' : undefined}>
                    <span className="num">{state === 'done' ? '✓' : n}</span>
                    {label}
                  </span>
                )}
              </li>
            )
          })}
        </ol>
      )}
      <Account />
    </header>
  )
}
