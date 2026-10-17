// "Projects" on screen 1: ready-made guides, then the guides you've opened before (src/projects.ts).
import { useState } from 'react'
import { forgetProject, READY_MADE, thumbnail, yourProjects, type Project } from '../projects'
import { designParams, navigate, withParams } from '../router'
import './ProjectsList.css'

function when(ms?: number) {
  if (!ms) return ''
  return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function Card({ project, onRemove }: { project: Project; onRemove?: () => void }) {
  const href = withParams('/guide', { design: project.design, code: designParams().code })
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
          src={thumbnail(project.design)}
          alt=""
          loading="lazy"
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
        />
        <span className="projects-title">{project.title}</span>
        {project.prompt && <span className="projects-prompt">{project.prompt}</span>}
        <span className="projects-meta">
          {[project.steps ? `${project.steps} steps` : '', when(project.openedAt)].filter(Boolean).join(' · ')}
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

export function ProjectsList() {
  const [mine, setMine] = useState(yourProjects)
  return (
    <section className="projects" id="projects">
      <h2 className="describe-sub">Ready-made guides</h2>
      <ul className="projects-grid">
        {READY_MADE.map((p) => (
          <Card key={p.design} project={p} />
        ))}
      </ul>
      <h2 className="describe-sub">Your projects</h2>
      {mine.length ? (
        <ul className="projects-grid">
          {mine.map((p) => (
            <Card
              key={p.design}
              project={p}
              onRemove={() => {
                forgetProject(p.design)
                setMine(yourProjects())
              }}
            />
          ))}
        </ul>
      ) : (
        <p className="projects-empty">Guides you open show up here, so you can come back to them. They're kept in this browser.</p>
      )}
    </section>
  )
}
