import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { configureAuth } from './lib/auth'
import './styles.css'

const isConfigured = configureAuth()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App isConfigured={isConfigured} />
  </StrictMode>,
)
