// Your projects: the guides this browser opened or designed, and the ones your own AI exported with
// your key (src/projects.ts).
import { ProgressHeader } from '../components/ProgressHeader'
import { YourProjects } from '../components/ProjectsList'
import './DescribePage.css'

export function ProjectsPage() {
  return (
    <div className="page">
      <ProgressHeader tab="projects" />
      <main className="page-body">
        <div className="describe-page">
          <section className="describe-main">
            <h1>Your projects</h1>
            <YourProjects />
          </section>
        </div>
      </main>
    </div>
  )
}
