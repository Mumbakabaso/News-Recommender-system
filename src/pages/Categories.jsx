import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import ArticleCard from '../components/ArticleCard'
import CategoryPills from '../components/CategoryPills'
import RegionToggle from '../components/RegionToggle'
import { useRegion } from '../hooks/useRegion'

export default function Categories() {
  const [categories, setCategories] = useState([])
  const [active, setActive] = useState(null)
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [region, setRegion] = useRegion()
  const [sources, setSources] = useState([])
  const [source, setSource] = useState('')

  useEffect(() => {
    api.getCategories().then((d) => setCategories(d.categories || [])).catch(() => {})
    api.getSources().then((d) => setSources(d.sources || [])).catch(() => {})
  }, [])

  // Only offer sources that match the region and actually have articles.
  // Several BBC feeds share the "BBC News" name, so group by display name.
  const sourceOptions = Object.values(
    sources
      .filter((s) => s.article_count > 0 && (!region || s.region === region))
      .reduce((acc, s) => {
        acc[s.name] = acc[s.name] || { name: s.name, keys: [] }
        acc[s.name].keys.push(s.key)
        return acc
      }, {}),
  )

  // Drop a source selection that no longer fits the chosen region.
  useEffect(() => {
    if (source && sources.length && !sourceOptions.some((o) => o.keys.join(',') === source)) setSource('')
  }, [region, sources])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .getArticles({ category: active, region, source: source || null, pageSize: 24 })
      .then((d) => setArticles(d.articles || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [active, region, source])

  const handleCardClick = ({ articleId, position }) => {
    api.logInteraction({ articleId, eventType: 'click', position }).catch(() => {})
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-xl font-semibold text-slate-900 mb-4">Browse by category</h1>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <RegionToggle value={region} onChange={setRegion} />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="text-sm border border-slate-200 rounded-lg bg-white px-3 py-2 text-slate-700"
          aria-label="Filter by news source"
        >
          <option value="">All sources</option>
          {sourceOptions.map((o) => (
            <option key={o.name} value={o.keys.join(',')}>{o.name}</option>
          ))}
        </select>
      </div>
      <div className="mb-6">
        <CategoryPills categories={categories} active={active} onSelect={setActive} />
      </div>

      {loading && <div className="text-slate-400 py-16 text-center">Loading articles…</div>}
      {error && (
        <div className="text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 text-sm">{error}</div>
      )}

      {!loading && !error && articles.length === 0 && (
        <div className="text-slate-400 py-16 text-center">No articles match these filters yet.</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {articles.map((a, i) => (
          <ArticleCard key={a.id} article={a} position={i} source="browse" onClick={handleCardClick} />
        ))}
      </div>
    </div>
  )
}
