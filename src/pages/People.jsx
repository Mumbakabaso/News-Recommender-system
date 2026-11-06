import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, Users } from 'lucide-react'
import { api } from '../lib/api'
import { Avatar } from '../components/people/ProfileBody'
import { usePeople } from '../context/PeopleContext'

const PAGE_SIZE = 24
const FILTERS = [
  { key: 'news', label: 'In the news' },
  { key: 'zambia', label: 'Zambian figures' },
  { key: 'all', label: 'Everyone' },
]

// /people — directory of everyone the system has identified in the news,
// Zambian public figures first. Clicking a card opens the quick profile;
// the name links to the full profile page.
export default function People() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const filter = params.get('filter') || 'news'
  const [input, setInput] = useState(q)
  const [people, setPeople] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { openPerson } = usePeople()

  useEffect(() => setInput(q), [q])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .listPeople({ q, zambian: filter === 'zambia', inNews: filter === 'news' && !q, page, pageSize: PAGE_SIZE })
      .then((d) => {
        setPeople((prev) => (page === 1 ? d.people : [...prev, ...d.people]))
        setTotal(d.total)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [q, filter, page])

  const update = (next) => {
    const p = new URLSearchParams(params)
    Object.entries(next).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)))
    setPage(1)
    setParams(p)
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Users className="w-6 h-6 text-indigo-600" /> People in the news
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Profiles of public figures mentioned in the news, with sources and the latest developments.
          </p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            update({ q: input.trim() })
          }}
          className="relative w-full sm:w-72"
        >
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Search a name, e.g. HH or Hichilema"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Search people"
          />
        </form>
      </div>

      <div className="flex gap-2 mb-6 overflow-x-auto">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => update({ filter: f.key === 'news' ? null : f.key })}
            className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap border ${
              filter === f.key ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
            }`}
          >
            {f.label}
          </button>
        ))}
        <span className="ml-auto self-center text-xs text-slate-400 whitespace-nowrap">{total} people</span>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {!loading && !error && people.length === 0 && (
        <p className="text-slate-500 text-sm">
          {q ? `No one found for “${q}”.` : 'No people identified yet. They appear as articles are scanned after each news refresh.'}
        </p>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {people.map((p) => (
          <div
            key={p.id}
            role="button"
            tabIndex={0}
            onClick={() => openPerson(p)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), openPerson(p))}
            className="flex gap-3 items-center bg-white border border-slate-200 rounded-xl p-4 text-left cursor-pointer hover:shadow-md hover:border-slate-300 transition focus-visible:outline-2 focus-visible:outline-indigo-500"
          >
            <Avatar person={p} size="md" />
            <div className="min-w-0">
              <Link
                to={`/people/${p.slug}`}
                onClick={(e) => e.stopPropagation()}
                className="font-semibold text-slate-900 hover:text-indigo-700 line-clamp-1"
              >
                {p.name}
              </Link>
              <p className="text-sm text-slate-500 line-clamp-2">{p.headline_position || p.short_description || '—'}</p>
              <div className="mt-1 flex gap-1.5">
                {p.is_zambian && (
                  <span className="text-[10.5px] font-semibold text-emerald-800 bg-emerald-50 px-1.5 rounded">Zambia</span>
                )}
                {p.verification === 'news_only' && (
                  <span className="text-[10.5px] font-semibold text-amber-800 bg-amber-50 px-1.5 rounded">News reports</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {people.length < total && (
        <div className="text-center mt-8">
          <button
            onClick={() => setPage((n) => n + 1)}
            disabled={loading}
            className="px-4 py-2 rounded-lg border border-slate-200 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {loading ? 'Loading…' : 'Show more'}
          </button>
        </div>
      )}
    </div>
  )
}
