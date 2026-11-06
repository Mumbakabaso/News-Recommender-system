import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, Newspaper, Lock } from 'lucide-react'
import { api } from '../lib/api'
import ArticleCard from '../components/ArticleCard'
import RegionToggle from '../components/RegionToggle'
import TrendingStrip from '../components/TrendingStrip'
import { useRegion } from '../hooks/useRegion'
import { signupUrl } from '../lib/redirect'

// Home page for logged-out visitors: trending stories and the latest
// headlines are open to everyone (as teasers); reading a full article and
// the personalised For You feed need a free account.
export default function PublicHome() {
  const [region, setRegion] = useRegion()
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api
      .getArticles({ region, pageSize: 12 })
      .then((d) => setArticles(d.articles || []))
      .catch(() => setArticles([]))
      .finally(() => setLoading(false))
  }, [region])

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <section className="mb-8 rounded-2xl bg-slate-900 text-white px-6 py-8 sm:px-10 sm:py-10 flex flex-col md:flex-row md:items-center gap-6 justify-between">
        <div className="max-w-xl">
          <div className="inline-flex items-center gap-1.5 text-xs font-medium bg-white/10 px-2.5 py-1 rounded-full mb-3">
            <Sparkles className="w-3.5 h-3.5" /> Personalised by reinforcement learning
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold leading-tight mb-2">
            Zambian and world news, picked for you
          </h1>
          <p className="text-slate-300 text-sm sm:text-base">
            Create a free account, choose the topics you care about, and your For You feed learns from what you
            read. An account also unlocks full articles.
          </p>
        </div>
        <div className="flex gap-3 shrink-0">
          <Link
            to={signupUrl({ next: '/', reason: 'foryou' })}
            className="bg-indigo-500 hover:bg-indigo-400 text-white text-sm font-medium px-5 py-2.5 rounded-lg"
          >
            Create free account
          </Link>
          <Link
            to="/login"
            className="bg-white/10 hover:bg-white/20 text-white text-sm font-medium px-5 py-2.5 rounded-lg"
          >
            Log in
          </Link>
        </div>
      </section>

      <div className="mb-6">
        <RegionToggle value={region} onChange={setRegion} />
      </div>

      <TrendingStrip region={region} />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper className="w-5 h-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-slate-900">Latest headlines</h2>
        </div>
        <span className="hidden sm:flex items-center gap-1 text-xs text-slate-500">
          <Lock className="w-3.5 h-3.5" /> Sign up to read full articles
        </span>
      </div>

      {loading && <div className="text-slate-400 py-16 text-center">Loading headlines…</div>}
      {!loading && articles.length === 0 && (
        <div className="text-slate-400 py-16 text-center">No articles yet — the backend may still be fetching news.</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {articles.map((a, i) => (
          <ArticleCard key={a.id} article={a} position={i} source="public-home" />
        ))}
      </div>
    </div>
  )
}
