import { designParams, navigate, withParams } from '../router'
import './ProgressHeader.css'

const STEPS = ['Describe', 'Design', 'Guide', 'Build', 'Print'] as const

interface Props {
  active: 1 | 2 | 3 | 4 | 5
  /** Overrides for links when the page knows more than the URL (e.g. the design page). */
  design?: string | null
  job?: string | null
}

/** "1 Describe ✓ · 2 Design · ..." across the top of every screen. */
export function ProgressHeader({ active, design, job }: Props) {
  const params = designParams()
  const d = design ?? params.design
  const j = job ?? params.job
  const code = params.code
  const href: Record<number, string | null> = {
    1: withParams('/', { code }),
    2: j ? withParams(`/design/${j}`, { code }) : null,
    3: d ? withParams('/guide', { design: d, job: j, code }) : null,
    4: d ? withParams('/guide', { design: d, job: j, code }) : null,
    5: d ? withParams('/print', { design: d, job: j, code }) : null,
  }
  return (
    <header className="progress-header">
      <a
        className="brand"
        href={href[1]!}
        onClick={(e) => {
          e.preventDefault()
          navigate(href[1]!)
        }}
      >
        Physical Studio
      </a>
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
    </header>
  )
}
