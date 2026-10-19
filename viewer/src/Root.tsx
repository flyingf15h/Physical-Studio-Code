import { useEffect } from 'react'
import { useRoute, type Route } from './router'
import App from './App'
import { NetworkBanner } from './components/NetworkBanner'
import { AccountPage } from './pages/AccountPage'
import { BuildPage } from './pages/BuildPage'
import { DescribePage } from './pages/DescribePage'
import { DesignPage } from './pages/DesignPage'
import { LegalPage, NotFoundPage } from './pages/LegalPage'
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

// The tab title for each screen; a build page replaces it with the build's own title once it loads.
const TITLES: Record<Route['page'], string> = {
  describe: 'Physical Studio · step-by-step Arduino build guides',
  projects: 'Your projects · Physical Studio',
  build: 'Build guide · Physical Studio',
  design: 'Designing · Physical Studio',
  guide: 'Guide · Physical Studio',
  print: 'Print and share · Physical Studio',
  legal: 'Physical Studio',
  notfound: 'Page not found · Physical Studio',
  account: 'Your account · Physical Studio',
}

function Page() {
  const route = useRoute()
  useEffect(() => {
    document.title =
      route.page === 'legal' ? `${route.doc[0].toUpperCase()}${route.doc.slice(1)} · Physical Studio` : TITLES[route.page]
  }, [route])
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
    case 'legal':
      return <LegalPage doc={route.doc} />
    case 'account':
      return <AccountPage />
    case 'notfound':
      return <NotFoundPage />
    default:
      return <App />
  }
}
