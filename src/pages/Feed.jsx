import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import ArticleCard from '../components/ArticleCard'
import RegionToggle from '../components/RegionToggle'
import TrendingStrip from '../components/TrendingStrip'
import { useRegion } from '../hooks/useRegion'
import { Sparkles, RefreshCcw, SlidersHorizontal, ThumbsUp } from 'lucide-react'

// The home feed is powered by the RL recommendation endpoint rather than
// a plain reverse-chronological list. Every card click is logged as a
// reward signal back to the bandit via api.logInteraction.
export default function Feed() {
  const { user, loading: authLoading } = useAuth()
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [region, setRegion] = useRegion()
  // Cards the reader disliked in this session: collapsed with an Undo.
  const [dismissed, setDismissed] = useState(() => new Set())

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getRecommendations({ count: 12, region })
      setArticles(data.articles || [])
      setDismissed(new Set())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Wait until we know who the user is, and don't fetch (which logs
  // impressions) for someone about to be sent to onboarding.
  const needsOnboarding = !!user?.needs_onboarding
  useEffect(() => {
    if (authLoading || needsOnboarding) return
    load()
  }, [authLoading, needsOnboarding, region])

  // Keep the local copy in sync, and collapse a card the moment it's disliked.
  const handleFeedback = (articleId, value) => {
    setArticles((prev) => prev.map((a) => (a.id === articleId ? { ...a, my_feedback: value } : a)))
    setDismissed((prev) => {
      const next = new Set(prev)
      if (value === -1) next.add(articleId)
      else next.delete(articleId)
      return next
    })
  }

  const undoDislike = async (articleId) => {
    try {
      await api.setFeedback(articleId, 0)
      handleFeedback(articleId, 0)
    } catch {
      // leave it collapsed if the undo didn't save
    }
  }

  const handleCardClick = ({ articleId, position }) => {
    api.logInteraction({ articleId, eventType: 'click', position }).catch(() => {})
  }

  // A signed-in user who hasn't picked interests yet goes to onboarding first.
  if (needsOnboarding) return <Navigate to="/onboarding" replace />

  const interests = user?.interests || []

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <RegionToggle value={region} onChange={setRegion} />
      </div>

      <TrendingStrip region={region} />

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-indigo-600" />
          <h1 className="text-xl font-semibold text-slate-900">Recommended for you</h1>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
        >
          <RefreshCcw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {user && (
        <div className="flex flex-wrap items-center gap-2 mb-6 text-sm">
          {interests.length > 0 ? (
            <>
              <span className="text-slate-500">Based on your interests:</span>
              {interests.map((slug) => (
                <span
                  key={slug}
                  className="px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 font-medium capitalize"
                >
                  {slug.replace('-', ' ')}
                </span>
              ))}
            </>
          ) : (
            <span className="text-slate-500">Pick a few interests to personalise your feed.</span>
          )}
          <Link
            to="/onboarding?edit=1"
            className="flex items-center gap-1 text-indigo-600 hover:text-indigo-700 font-medium ml-1"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" /> {interests.length > 0 ? 'Edit' : 'Choose interests'}
          </Link>
          <Link to="/liked" className="flex items-center gap-1 text-slate-500 hover:text-slate-900 font-medium ml-2">
            <ThumbsUp className="w-3.5 h-3.5" /> Your likes
          </Link>
        </div>
      )}

      {loading && <div className="text-slate-400 py-16 text-center">Loading recommendations…</div>}
      {error && (
        <div className="text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 text-sm">
          Couldn't load recommendations: {error}
        </div>
      )}

      {!loading && !error && articles.length === 0 && (
        <div className="text-slate-400 py-16 text-center">
          {region === 'zambia'
            ? 'No Zambian articles yet — the backend may still be fetching the local news feeds.'
            : 'No articles yet — the backend may still be ingesting news.'}
        </div>
      )}

      {articles.length > 0 && (
        <p className="text-xs text-slate-400 mb-3">
          Use the thumbs up / down on any story to tell the recommender what you want more or less of.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {articles.map((a, i) => (
          <ArticleCard
            key={a.id}
            article={a}
            position={i}
            source="recommendation"
            onClick={handleCardClick}
            onFeedback={handleFeedback}
            dismissed={dismissed.has(a.id)}
            onUndo={undoDislike}
          />
        ))}
      </div>
    </div>
  )
}
