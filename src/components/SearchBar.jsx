import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Search, X } from 'lucide-react'

// Header search box. Submitting goes to /search?q=..., and the box keeps
// showing the current query while you're on the results page.
export default function SearchBar({ className = '', autoFocus = false }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const current = location.pathname === '/search' ? params.get('q') || '' : ''
  const [value, setValue] = useState(current)

  useEffect(() => {
    setValue(current)
  }, [current])

  const submit = (e) => {
    e.preventDefault()
    const q = value.trim()
    if (!q) return
    const next = new URLSearchParams(location.pathname === '/search' ? params : undefined)
    next.set('q', q)
    navigate(`/search?${next.toString()}`)
  }

  return (
    <form onSubmit={submit} role="search" className={`relative ${className}`}>
      <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search news…"
        aria-label="Search news"
        autoFocus={autoFocus}
        className="w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-8 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          onClick={() => setValue('')}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-700"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </form>
  )
}
