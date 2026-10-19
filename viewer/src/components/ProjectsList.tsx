// Projects on screen 1: the ready-made guides, and your own (opened here or exported by your AI; src/projects.ts).
import { useEffect, useState } from 'react'
import { listMyProjects, listSaved } from '../api'
import { useUser } from '../auth'
import { forgetProject, LEVELS, projectHref, READY_MADE, savedKey, thumbnail, yourProjects, type Level, type Project } from '../projects'
import { designParams, navigate } from '../router'
import './ProjectsList.css'

function when(ms?: number) {
  if (!ms) return ''
  return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function Card({ project, onRemove }: { project: Project; onRemove?: () => void }) {
  const href = projectHref(project.design, designParams().code)
  return (
    <li className="projects-card">
      <a
        href={href}
        onClick={(e) => {
          e.preventDefault()
          navigate(href)
        }}
      >
        <img
          src={project.thumb ?? thumbnail(project.design, project.steps)}
          alt=""
          loading="lazy"
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
        />
        <span className="projects-title">{project.title}</span>
        {project.prompt && <span className="projects-prompt">{project.prompt}</span>}
        <span className="projects-meta">
          {project.level && <span className={`level level-${project.level.toLowerCase()}`}>{project.level}</span>}
          {[
            project.steps ? `${project.steps} step${project.steps === 1 ? '' : 's'}` : '',
            project.minutes ? duration(project.minutes) : '',
            when(project.openedAt),
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </a>
      {onRemove && (
        <button type="button" className="projects-remove" title="Remove from your projects" onClick={onRemove}>
          ×
        </button>
      )}
    </li>
  )
}

/** The guides you opened here, plus the ones your AI exported with your key, newest first. */
function merge(opened: Project[], exported: Project[]): Project[] {
  const byDesign = new Map<string, Project>()
  for (const p of [...exported, ...opened]) {
    const seen = byDesign.get(p.design)
    if (!seen || (p.openedAt ?? 0) > (seen.openedAt ?? 0)) byDesign.set(p.design, { ...seen, ...p })
  }
  return [...byDesign.values()].sort((a, b) => (b.openedAt ?? 0) - (a.openedAt ?? 0))
}

const duration = (minutes: number) => (minutes < 90 ? `about ${minutes} min` : `about ${Math.round(minutes / 60)} h`)

export function ReadyMadeGuides() {
  const [level, setLevel] = useState<Level | null>(null)
  const shown = READY_MADE.filter((p) => !level || p.level === level)
  return (
    <>
      <div className="level-filter" role="group" aria-label="Filter by difficulty">
        {[null, ...LEVELS].map((l) => (
          <button
            key={l ?? 'all'}
            type="button"
            className={l === level ? 'active' : ''}
            aria-pressed={l === level}
            onClick={() => setLevel(l)}
          >
            {l ?? 'All'} ({READY_MADE.filter((p) => !l || p.level === l).length})
          </button>
        ))}
      </div>
      <ul className="projects-grid">
        {shown.map((p) => (
          <Card key={p.design} project={p} />
        ))}
      </ul>
    </>
  )
}

/** keyVersion: bump it when a new key is saved, so its projects are fetched. Also refetched when
 * the tab gets focus again, since the visitor's AI exports while they're in another window. */
export function YourProjects({ keyVersion = 0 }: { keyVersion?: number }) {
  const user = useUser()
  const [opened, setOpened] = useState(yourProjects)
  const [exported, setExported] = useState<Project[]>([])
  const [saved, setSaved] = useState<Project[]>([])
  useEffect(() => {
    const load = () => {
      setOpened(yourProjects())
      if (user)
        listSaved().then(
          (list) =>
            setSaved(
              list.map((p) => ({
                design: p.design,
                title: p.title,
                prompt: p.prompt,
                steps: p.steps,
                openedAt: p.updated * 1000,
              })),
            ),
          () => setSaved([]),
        )
      else setSaved([])
      const key = savedKey()
      if (!key) return
      listMyProjects(key).then(
        (list) =>
          setExported(
            list.map((p) => ({
              design: p.design,
              title: p.title,
              prompt: p.prompt,
              steps: p.steps,
              openedAt: p.at * 1000,
            })),
          ),
        () => setExported([]),
      )
    }
    load()
    window.addEventListener('focus', load)
    return () => window.removeEventListener('focus', load)
  }, [keyVersion, user])
  const mine = merge([...opened, ...saved], exported)
  return (
    <section className="projects" id="projects">
      {mine.length ? (
        <ul className="projects-grid">
          {mine.map((p) => (
            <Card
              key={p.design}
              project={p}
              onRemove={() => {
                forgetProject(p.design)
                setOpened(yourProjects())
                setExported(exported.filter((q) => q.design !== p.design))
                setSaved(saved.filter((q) => q.design !== p.design))
              }}
            />
          ))}
        </ul>
      ) : (
        <p className="projects-empty">
          Nothing here yet. Design something on the Dashboard, or open a ready-made guide.
        </p>
      )}
    </section>
  )
}
