import { useRoute } from './router'
import App from './App'
import { NetworkBanner } from './components/NetworkBanner'
import { BuildPage } from './pages/BuildPage'
import { DescribePage } from './pages/DescribePage'
import { DesignPage } from './pages/DesignPage'
import { PrintPage } from './pages/PrintPage'
import { ProjectsPage } from './pages/ProjectsPage'

export default function Root() {
  return (
    <>
      <Page />
      <NetworkBanner />
    </>
  )
}

function Page() {
  const route = useRoute()
  switch (route.page) {
    case 'describe':
      return <DescribePage />
    case 'build':
      return <BuildPage key={route.buildId} buildId={route.buildId} />
    case 'projects':
      return <ProjectsPage />
    case 'design':
      return <DesignPage key={route.jobId} jobId={route.jobId} />
    case 'print':
      return <PrintPage />
    default:
      return <App />
  }
}
