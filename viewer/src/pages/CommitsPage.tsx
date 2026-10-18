// Commits: every commit of your breadboard builds, newest build first, shown the way Senna's Build
// helper Commits tab shows them (BuildPage's Commits list): #0 is what you had at the start, then
// each step you committed, with its photos, the AI's check and a 3D model of that commit.
import { useEffect, useState } from 'react'
import { getBuild, listSaved, type Build } from '../api'
import { useUser } from '../auth'
import { ProgressHeader } from '../components/ProgressHeader'
import { yourProjects } from '../projects'
import { designParams, navigate, withParams } from '../router'
import { Commits } from './BuildPage'
import './DescribePage.css'
import './BuildPage.css'

export function CommitsPage() {
  const user = useUser()
  const [builds, setBuilds] = useState<Build[] | null>(null)
  const code = designParams().code

  useEffect(() => {
    let stop = false
    const load = async () => {
      const saved = user ? await listSaved().catch(() => []) : []
      const ids = [...new Set([...yourProjects(), ...saved].map((p) => p.design).filter((d) => d.startsWith('build/')))]
      const found = await Promise.all(ids.map((d) => getBuild(d.slice(6)).catch(() => null)))
      if (!stop) setBuilds(found.filter((b): b is Build => !!b && b.status === 'done' && !!b.plan))
    }
    void load()
    return () => {
      stop = true
    }
  }, [user])

  return (
    <div className="page">
      <ProgressHeader tab="commits" />
      <main className="page-body">
        <div className="describe-page">
          <section className="describe-main">
            <h1>Commits</h1>
            {builds === null ? (
              <p className="muted">Loading your commits…</p>
            ) : builds.length === 0 ? (
              <p className="projects-empty">
                No commits yet. Start a build on the Dashboard: what you have on your bench becomes commit #0, and each
                step you photograph becomes a commit.
              </p>
            ) : (
              builds.map((b) => {
                const href = withParams(`/build/${b.id}`, { code })
                return (
                  <section key={b.id} className="commits-build">
                    <h2>
                      <a
                        href={href}
                        onClick={(e) => {
                          e.preventDefault()
                          navigate(href)
                        }}
                      >
                        {b.plan!.title}
                      </a>
                      <span className="muted">
                        {' '}
                        · {b.commits.length} commit{b.commits.length === 1 ? '' : 's'}
                      </span>
                    </h2>
                    <Commits build={b} plan={b.plan!} />
                  </section>
                )
              })
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
