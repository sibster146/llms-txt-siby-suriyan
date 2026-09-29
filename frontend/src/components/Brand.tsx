import { FileText } from 'lucide-react'

export function Brand() {
  return (
    <a className="brand" href="/" aria-label="llms.txt home">
      <span className="brand-mark"><FileText size={18} /></span>
      llms.txt
    </a>
  )
}
