import { useRoute } from './router'
import App from './App'
import { DescribePage } from './pages/DescribePage'
import { DesignPage } from './pages/DesignPage'
import { PrintPage } from './pages/PrintPage'

export default function Root() {
  const route = useRoute()
  switch (route.page) {
    case 'describe':
      return <DescribePage />
    case 'design':
      return <DesignPage key={route.jobId} jobId={route.jobId} />
    case 'print':
      return <PrintPage />
    default:
      return <App />
  }
}
