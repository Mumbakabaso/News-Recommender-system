import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search as SearchIcon, Hash } from 'lucide-react'
import { api } from '../lib/api'
import ArticleCard from '../components/ArticleCard'
import CategoryPills from '../components/CategoryPills'
import RegionToggle from '../components/RegionToggle'
import SearchBar from '../components/SearchBar'
import { useRegion } from '../hooks/useRegion'

const PAGE_SIZE = 18

export default function Search() {
  const [params, setParams] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const category = params.get('category') || null
  const [region, setRegion] = useRegion()

  const [categories, setCategories] = useState([])
  const [articles, setArticles] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [hotTopics, setHotTopics] = useState([])

  useEffect(() => {
    api.getCategories().then((d) => setCategories(d.categories || [])).catch(() => {})
    api.getTrending({ limit: 1 }).then((d) => setHotTopics(d.hot_topics || [])).catch(() => {})
  }, [])

  // New query / filters -> start again from page 1.
  useEffect(() => {
    if (!q) {
      setArticles([])
      setTotal(0)
      return
    }
    setLoading(true)
    setError(null)
    setPage(1)
    api
      .search({ q, region, category, page: 1, pageSize: PAGE_SIZE })
      .then((d) => {
        setArticles(d.articles || [])
        setTotal(d.total || 0)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [q, region, category])

  const loadMore = () => {
    const next = page + 1
    setLoading(true)
    api
      .search({ q, region, category, page: next, pageSize: PAGE_SIZE })
      .then((d) => {
        setArticles((prev) => [...prev, ...(d.articles || [])])
        setPage(next)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  const setCategory = (c) => {
    const next = new URLSearchParams(params)
    if (c) next.set('category', c)
    else next.delete('category')
    setParams(next)
  }

  const handleCardClick = ({ articleId, position }) => {
    api.logInteraction({ articleId, eventType: 'click', position }).catch(() => {})
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* On small screens the header search box is hidden, so show one here. */}
      <SearchBar className="md:hidden mb-6" autoFocus={!q} />

      {q ? (
        <h1 className="text-xl font-semibold text-slate-900 mb-4">
          Results for <span className="text-indigo-600">“{q}”</span>
        </h1>
      ) : (
        <h1 className="text-xl font-semibold text-slate-900 mb-4">Search news</h1>
      )}

      <div className="flex flex-col items-start gap-3 mb-6">
        <RegionToggle value={region} onChange={setRegion} />
        <CategoryPills categories={categories} active={category} onSelect={setCategory} />
      </div>

      {q && !loading && !error && (
        <p className="text-sm text-slate-500 mb-4">
          {total === 0 ? 'No articles found.' : `${total} article${total === 1 ? '' : 's'} found`}
        </p>
      )}

      {error && (
        <div className="text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 text-sm mb-4">{error}</div>
      )}

      {(!q || (!loading && total === 0)) && (
        <div className="py-10 text-center">
          <SearchIcon className="w-8 h-8 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 mb-1">
            {q ? 'Try a different word, or remove a filter.' : 'Search headlines and summaries from every source.'}
          </p>
          <p className="text-xs text-slate-400 mb-5">
            Tip: use “quotes” for an exact phrase, and -word to exclude a word.
          </p>
          {hotTopics.length > 0 && (
            <div className="flex flex-wrap justify-center gap-2">
              {hotTopics.slice(0, 10).map((t) => (
                <Link
                  key={t.topic}
                  to={`/search?q=${encodeURIComponent(t.topic)}`}
                  className="flex items-center gap-1 text-sm px-2.5 py-1 rounded-full bg-orange-50 text-orange-700 hover:bg-orange-100"
                >
                  <Hash className="w-3 h-3" />
                  {t.topic}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {articles.map((a, i) => (
          <ArticleCard key={a.id} article={a} position={i} source="search" onClick={handleCardClick} highlight={q} />
        ))}
      </div>

      {loading && <div className="text-slate-400 py-10 text-center">Searching…</div>}

      {!loading && articles.length < total && (
        <div className="text-center mt-8">
          <button
            onClick={loadMore}
            className="px-4 py-2 text-sm font-medium border border-slate-200 bg-white rounded-lg hover:bg-slate-50"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  )
}
