// Your projects: the guides this browser opened or designed, and the ones your own AI exported with
// your key (src/projects.ts).
import { ProgressHeader } from '../components/ProgressHeader'
import { YourProjects } from '../components/ProjectsList'
import './DescribePage.css'

export function ProjectsPage() {
  return (
    <div className="page">
      <ProgressHeader tab="projects" />
      <main className="page-body describe-page">
        <section className="describe-main">
          <h1>Your projects</h1>
          <p className="describe-lede">
            Every guide you designed or opened in this browser, plus the ones your own AI exported with your key.
          </p>
          <YourProjects />
        </section>
      </main>
    </div>
  )
}
