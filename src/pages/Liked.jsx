import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ThumbsUp, ThumbsDown, ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'
import ArticleCard from '../components/ArticleCard'

const TABS = [
  { value: 'like', label: 'Liked', Icon: ThumbsUp },
  { value: 'dislike', label: 'Disliked', Icon: ThumbsDown },
]

// The reader's own feedback history: what they've liked / disliked, and a
// per-topic summary of what they've told the recommender.
export default function Liked() {
  const [tab, setTab] = useState('like')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = (value) => {
    setData(null)
    setError(null)
    api.getMyFeedback({ value }).then(setData).catch((e) => setError(e.message))
  }

  useEffect(() => {
    load(tab)
  }, [tab])

  // Removing a reaction here drops the article from the current list.
  const handleFeedback = (articleId, value) => {
    const keep = (tab === 'like' && value === 1) || (tab === 'dislike' && value === -1)
    if (!keep) {
      setData((d) => d && { ...d, articles: d.articles.filter((a) => a.id !== articleId), total: d.total - 1 })
    }
  }

  const summary = Object.entries(data?.by_category || {})
    .map(([category, c]) => ({ category, ...c }))
    .sort((a, b) => b.likes - b.dislikes - (a.likes - a.dislikes))

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <Link to="/" className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-4">
        <ArrowLeft className="w-4 h-4" /> Back to For You
      </Link>
      <h1 className="text-xl font-semibold text-slate-900 mb-1">Your feedback</h1>
      <p className="text-sm text-slate-500 mb-6">
        Stories you've liked or disliked. Your For You feed uses these to show you more of what you want.
      </p>

      {summary.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-6">
          {summary.map((s) => (
            <span
              key={s.category}
              className="text-sm px-3 py-1 rounded-full bg-white border border-slate-200 text-slate-700 capitalize"
            >
              {s.category.replace('-', ' ')}
              <span className="ml-2 text-emerald-600">+{s.likes}</span>
              <span className="ml-1 text-rose-600">−{s.dislikes}</span>
            </span>
          ))}
        </div>
      )}

      <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 mb-6" role="tablist">
        {TABS.map(({ value, label, Icon }) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium ${
              tab === value ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <Icon className="w-3.5 h-3.5" /> {label}
          </button>
        ))}
      </div>

      {error && <div className="text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 text-sm">{error}</div>}
      {!data && !error && <div className="text-slate-400 py-16 text-center">Loading…</div>}
      {data && data.articles.length === 0 && (
        <div className="text-slate-400 py-16 text-center">
          {tab === 'like'
            ? "You haven't liked any stories yet. Use the thumbs up on stories you enjoy."
            : "You haven't disliked any stories."}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {data?.articles.map((a, i) => (
          <ArticleCard key={a.id} article={a} position={i} source="liked" onFeedback={handleFeedback} />
        ))}
      </div>
    </div>
  )
}
