import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

function App() {
  const [status, setStatus] = useState('Connecting…')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/health', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Health check failed')
        const data = await response.json()
        setStatus(data.status === 'ok' ? 'Connected' : 'Unavailable')
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setStatus('Offline — start the backend')
      })
    return () => controller.abort()
  }, [])

  return (
    <main>
      <p className="eyebrow">HACKCAMP 2026</p>
      <h1>Open-Source Corpus Explorer</h1>
      <p>Discover the health of the open-source projects you depend on.</p>
      <div className="status" role="status">API: {status}</div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
